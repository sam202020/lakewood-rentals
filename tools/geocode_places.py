#!/usr/bin/env python3
"""Fill places.json with OpenStreetMap coordinates for any new place names.

  python3 tools/geocode_places.py            # geocode names not yet in places.json
  python3 tools/geocode_places.py --retry    # also retry names marked unresolved

Run it locally after a weekly refresh reports unknown locations. It uses the
public Nominatim service (1 request/second, as its usage policy requires) and
sends only place names plus "NJ" - nothing about visitors or the owner.
Entries with "source": "manual" are never touched.
"""
import argparse, json, pathlib, re, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import geo  # noqa: E402

# lon_min, lat_max, lon_max, lat_min - Lakewood, Jackson, Toms River, Howell, Manchester
VIEWBOX = "-74.45,40.25,-74.05,39.90"
UA = "lakewood-rentals-geocoder/1.0 (open-source rental list)"


def search(query):
    qs = urllib.parse.urlencode({
        "q": query, "format": "jsonv2", "limit": 3, "viewbox": VIEWBOX, "bounded": 1,
    })
    req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + qs,
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def lookup(key):
    full = geo.expand_abbreviations(key)
    queries = [f"{key}, Lakewood, NJ", f"{key}, NJ"]
    if full != key:
        queries = [f"{full}, Lakewood, NJ", f"{full}, NJ"] + queries
    if key in geo.TOWNS:
        queries = [f"{key} Township, NJ", f"{key}, NJ"]
    for q in queries:
        time.sleep(1.1)
        for hit in search(q):
            lat, lng = float(hit["lat"]), float(hit["lon"])
            if geo.plausible(lat, lng):
                return {"lat": round(lat, 5), "lng": round(lng, 5), "source": "osm",
                        "match": hit.get("display_name", "")[:90],
                        "kind": f"{hit.get('category', '')}/{hit.get('type', '')}"}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry", action="store_true")
    args = ap.parse_args()

    places = geo.load_places()
    listings = json.loads((ROOT / "listings.json").read_text())["listings"]
    todo = []
    for x in listings:
        # description words that slipped into a location ("KITCHENETTE. PRIVATE") are never places
        parts = [p for p in re.split(r"\s*/\s*|,\s*", x["location"]) if not geo.looks_like_description(p)]
        for k in geo.location_parts(" / ".join(parts)):
            e = places.get(k) or geo._known(places, k)
            if k in todo or (e and e.get("source") == "manual"):
                continue
            if e is None or (args.retry and e.get("source") == "unresolved"):
                todo.append(k)
    print(f"{len(todo)} names to geocode")
    for i, k in enumerate(todo, 1):
        res = lookup(k)
        places[k] = ({"name": k.title(), **res} if res else
                     {"name": k.title(), "lat": None, "lng": None, "source": "unresolved"})
        print(f"[{i}/{len(todo)}] {k:28} -> " + (f"{res['lat']},{res['lng']}  {res['match'][:50]}" if res else "unresolved"),
              flush=True)
        (ROOT / "places.json").write_text(json.dumps(dict(sorted(places.items())), indent=1, ensure_ascii=False))
    print("done")


if __name__ == "__main__":
    main()
