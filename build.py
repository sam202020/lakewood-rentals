#!/usr/bin/env python3
"""Build the static Lakewood NJ Area Rentals site.

  python3 build.py            # fetch live PDF, parse, write docs/index.html (+ sitemap.xml, robots.txt)
  python3 build.py --pdf X    # use a local PDF file instead of fetching

Safety: the parsed listings go through checks.py before anything is written.
If a hard check fails (count collapsed, locations/phones missing, ...) the
build aborts with exit code 1 and leaves listings.json and docs/index.html
untouched, so a PDF layout change never replaces a good site with a bad one.
Soft problems are printed as WARN lines; the build still succeeds.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys, datetime

import checks
import geo
import parse as P
import seo

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "listings.json"
TEMPLATE = ROOT / "site" / "template.html"
SEARCH_CORE = ROOT / "site" / "search-core.js"
LEAFLET_CSS = ROOT / "site" / "leaflet.css"     # Leaflet 1.9.4 (BSD-2), inlined because artifact pages may not load stylesheets
OUT = ROOT / "docs" / "index.html"
STREETS = ROOT / "streets.json"      # built by tools/build_streets.py; optional


def counter_code(path=ROOT / "data" / "analytics.json"):
    """The GoatCounter site code from data/analytics.json, or "" (no counting) if unset or not a plain code."""
    try:
        code = str(json.loads(pathlib.Path(path).read_text()).get("goatcounter", "")).strip().lower()
    except (OSError, ValueError, AttributeError):
        return ""
    return code if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", code) else ""


def previous_count():
    try:
        return json.loads(DATA.read_text()).get("count")
    except (OSError, ValueError):
        return None


def locate(listings, places):
    """Put every listing on the map (in place); returns the town centres used for "Jackson"-style listings."""
    also = geo.load_neighborhood_also()
    for x in listings:
        areas = geo.listing_areas(x["location"], also, places)   # listed under each of these neighbourhoods too
        if areas:
            x["areas"] = areas
        else:
            x.pop("areas", None)
        g = geo.resolve(x["location"], places)
        x["lat"], x["lng"] = g["lat"], g["lng"]
        x["geo"] = g["precision"]            # "place", "town" or None
        x["geo_unknown"] = g["unknown"]      # names missing from places.json
        x["geo_unverified"] = g["unverified"]  # names on an unchecked OSM pin
        x["geo_spread"] = g["spread"]          # miles between the places an averaged pin sits among
        if geo.looks_like_address(x["location"]):   # an address is never a neighbourhood: remember where it was mapped
            e = places.get(geo.normalize(x["location"])) or {}
            x["geo_neighborhood"] = e.get("neighborhood")

    # "Jackson" / "Toms River" alone mean the Jewish area there (the average of the places named in that town), not the township centre
    centers = geo.town_centers(listings, places)
    geo.apply_town_centers(listings, centers)
    return centers


def make_data(listings, list_date, places, centers, seen):
    """Everything the page needs, from located listings and the curated files. Writes nothing.

    `seen` is the neighbourhood names earlier builds showed (data/neighborhoods_seen.json)."""
    # the "Neighborhoods" index/browse list: every name ever seen, so one week's empty PDF slot
    # for a neighbourhood doesn't make it disappear from the list (owner, 2026-11-26)
    nb_counts = geo.neighborhood_counts(listings, sorted({P.tidy_location(n) for n in seen}))

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "list_date": list_date,
        "source_url": P.SOURCE_URL,
        "source_site": "https://masaumatan.com",
        "count": len(listings),
        "listings": listings,
        "neighborhoods": [{"name": k, "n": nb_counts[k]} for k in sorted(nb_counts)],
        # resolved places only, for the page's "Near" picker
        "places": {k: {"name": e.get("name") or k.title(), "lat": centers[k.title()]["lat"] if k.title() in centers and k in geo.TOWNS else e["lat"],
                       "lng": centers[k.title()]["lng"] if k.title() in centers and k in geo.TOWNS else e["lng"]}
                   for k, e in places.items() if e.get("lat") is not None},
        # tidy, de-duplicated names for the "Near" drop-down
        "picker": geo.picker_entries(places),
    }
    for item in data["picker"]:                    # the town entries ("Jackson") sit in the Jewish area too
        c = centers.get(item["name"])
        if c and item["name"].lower() in geo.TOWNS:
            item["lat"], item["lng"] = c["lat"], c["lng"]
    # every street in the area, so any street can be searched ("nearest this street")
    try:
        streets, data["picker"] = geo.streets_for_page(json.loads(STREETS.read_text()), data["picker"])
    except (OSError, ValueError):
        streets = None
    if streets:
        data["streets"] = streets
    data["preferred"] = geo.load_preferred_streets()
    data["area_streets"] = geo.load_area_streets()            # streets that are also listed as areas
    # shuls (Google Maps), so "near this shul" works. A shul that is also a neighbourhood ("Kol Shimshon",
    # "Bais Medrash Lutzk"/"Lutzk", BMG) is listed once, as the neighbourhood.
    all_shuls = geo.load_shuls()
    # every shul as a marker on the map (also the ones merged into a neighbourhood in the drop-down)
    data["shulpins"] = [[x["name"], x["lat"], x["lng"], x["town"], x["address"]] for x in all_shuls]
    shuls, data["picker"] = geo.merge_shuls(all_shuls, data["picker"])
    if shuls:
        data["shuls"] = [[s["name"], s["lat"], s["lng"], s["town"], s["address"]] + ([s["aka"]] if s["aka"] else [])
                         for s in shuls]
    data["counter"] = counter_code()          # anonymous visit / call-tap counts ("" = off)
    return data


def list_warnings(data):
    """WARN lines for listings that are in neither the Neighborhood nor the Street list. The lists are grouped by the
    page's own script, so this runs it with Node (tools/check_lists.js)."""
    node = shutil.which("node")
    if not node:
        return ["NOTE: Node is not installed, so the neighbourhood and street lists were not checked"]
    try:
        r = subprocess.run([node, str(ROOT / "tools" / "check_lists.js")], input=json.dumps(data), capture_output=True,
                           text=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError) as e:
        return [f"WARN: could not check the neighbourhood and street lists: {e}"]
    return r.stdout.splitlines()


def embed_json(data):
    """The data block inside the page. Listing text comes from advertisers, so "<" is written as \\u003c: no text can
    close the <script> block and become part of the page (JSON.parse reads it back as "<")."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def render_page(data):
    """The complete public page: a full HTML document (standards mode), the template split at its <!--__BODY__--> mark."""
    head, mark, body = TEMPLATE.read_text().partition("<!--__BODY__-->")
    if not mark:
        raise ValueError("site/template.html lost its <!--__BODY__--> mark")
    head = head.replace(
        "<!--__SEO__-->", seo.head_tags(data["count"], data["list_date"])
    ).replace(
        "/*__LEAFLET_CSS__*/", LEAFLET_CSS.read_text()
    )
    body = body.replace(
        "/*__SEARCH_CORE__*/", SEARCH_CORE.read_text()
    ).replace(
        "/*__DATA__*/null", embed_json(data)       # last, so nothing in the data is ever treated as a placeholder
    )
    return ('<!doctype html>\n<html lang="en">\n<head>\n' + head.rstrip() +
            '\n<link rel="icon" href="favicon.svg" type="image/svg+xml">\n</head>\n<body>\n' +
            body.strip() + "\n</body>\n</html>\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="local PDF path (default: fetch live)")
    args = ap.parse_args()

    src = args.pdf or P.SOURCE_URL
    list_date, listings = P.parse(P.fetch_pdf(src))
    for page_no, text in P.SKIPPED:
        print(f"NOTE: left out an ad banner on page {page_no}: {text}")

    places = geo.load_places()
    centers = locate(listings, places)

    errors, warnings = checks.check(listings, previous_count())
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ABORT: {e}", file=sys.stderr)
        print("Keeping existing listings.json and docs/index.html unchanged.", file=sys.stderr)
        sys.exit(1)

    data = make_data(listings, list_date, places, centers, geo.load_neighborhoods_seen())
    for line in list_warnings(data):
        print(line)
    geo.NEIGHBORHOODS_SEEN_FILE.write_text(
        json.dumps(sorted(n["name"] for n in data["neighborhoods"]), indent=2, ensure_ascii=False) + "\n")
    # listings.json stays small and readable: the street lines live in streets.json and only go into the page
    DATA.write_text(json.dumps({k: v for k, v in data.items() if k != "streets"}, indent=2, ensure_ascii=False))

    OUT.write_text(render_page(data))
    # for search engines, next to the page
    (OUT.parent / "sitemap.xml").write_text(seo.sitemap(list_date))
    (OUT.parent / "robots.txt").write_text(seo.robots())
    print(f"built {OUT}  ({len(listings)} listings, list_date={list_date!r}, "
          f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''})")


if __name__ == "__main__":
    main()
