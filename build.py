#!/usr/bin/env python3
"""Build the static Lakewood NJ Area Rentals site.

  python3 build.py            # fetch live PDF, parse, write docs/index.html
  python3 build.py --pdf X    # use a local PDF file instead of fetching

Safety: the parsed listings go through checks.py before anything is written.
If a hard check fails (count collapsed, locations/phones missing, ...) the
build aborts with exit code 1 and leaves listings.json and docs/index.html
untouched, so a PDF layout change never replaces a good site with a bad one.
Soft problems are printed as WARN lines; the build still succeeds.
"""
import argparse, json, pathlib, sys, datetime

import checks
import geo
import parse as P

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "listings.json"
TEMPLATE = ROOT / "site" / "template.html"
SEARCH_CORE = ROOT / "site" / "search-core.js"
LEAFLET_CSS = ROOT / "site" / "leaflet.css"     # Leaflet 1.9.4 (BSD-2), inlined because artifact pages may not load stylesheets
OUT = ROOT / "docs" / "index.html"
STREETS = ROOT / "streets.json"      # built by tools/build_streets.py; optional


def previous_count():
    try:
        return json.loads(DATA.read_text()).get("count")
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="local PDF path (default: fetch live)")
    args = ap.parse_args()

    src = args.pdf or P.SOURCE_URL
    list_date, listings = P.parse(P.fetch_pdf(src))
    for page_no, text in P.SKIPPED:
        print(f"NOTE: left out an ad banner on page {page_no}: {text}")

    places = geo.load_places()
    for x in listings:
        g = geo.resolve(x["location"], places)
        x["lat"], x["lng"] = g["lat"], g["lng"]
        x["geo"] = g["precision"]            # "place", "town" or None
        x["geo_unknown"] = g["unknown"]      # names missing from places.json
        x["geo_unverified"] = g["unverified"]  # names on an unchecked OSM pin
        x["geo_spread"] = g["spread"]          # miles between the places an averaged pin sits among
        if geo.looks_like_address(x["location"]):   # an address is never a neighbourhood: remember where it was mapped
            e = places.get(geo.normalize(x["location"])) or {}
            x["geo_neighborhood"] = e.get("neighborhood")

    errors, warnings = checks.check(listings, previous_count())
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ABORT: {e}", file=sys.stderr)
        print("Keeping existing listings.json and docs/index.html unchanged.", file=sys.stderr)
        sys.exit(1)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "list_date": list_date,
        "source_url": P.SOURCE_URL,
        "source_site": "https://masaumatan.com",
        "count": len(listings),
        "listings": listings,
        # resolved places only, for the page's "Near" picker
        "places": {k: {"name": e.get("name") or k.title(), "lat": e["lat"], "lng": e["lng"]}
                   for k, e in places.items() if e.get("lat") is not None},
        # tidy, de-duplicated names for the "Near" drop-down
        "picker": geo.picker_entries(places),
    }
    # every street in the area, so any street can be searched ("nearest this street")
    try:
        streets, data["picker"] = geo.streets_for_page(json.loads(STREETS.read_text()), data["picker"])
    except (OSError, ValueError):
        streets = None
    if streets:
        data["streets"] = streets
    # shuls (Google Maps), so "near this shul" works. A shul that is also a neighbourhood ("Kol Shimshon",
    # "Bais Medrash Lutzk"/"Lutzk", BMG) is listed once, as the neighbourhood.
    shuls, data["picker"] = geo.merge_shuls(geo.load_shuls(), data["picker"])
    if shuls:
        data["shuls"] = [[s["name"], s["lat"], s["lng"], s["town"], s["address"]] + ([s["aka"]] if s["aka"] else [])
                         for s in shuls]
    # listings.json stays small and readable: the street lines live in streets.json and only go into the page
    DATA.write_text(json.dumps({k: v for k, v in data.items() if k != "streets"}, indent=2, ensure_ascii=False))

    html = TEMPLATE.read_text().replace(
        "/*__LEAFLET_CSS__*/", LEAFLET_CSS.read_text()
    ).replace(
        "/*__SEARCH_CORE__*/", SEARCH_CORE.read_text()
    ).replace(
        "/*__DATA__*/null",
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )
    OUT.write_text(html)
    print(f"built {OUT}  ({len(listings)} listings, list_date={list_date!r}, "
          f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''})")


if __name__ == "__main__":
    main()
