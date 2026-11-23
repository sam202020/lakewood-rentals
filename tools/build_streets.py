#!/usr/bin/env python3
"""Build streets.json: every named street around Lakewood, as simplified lines, for "sort by nearest this street".

  python3 tools/build_streets.py --fetch      # download town borders + streets from OpenStreetMap (Overpass), then build
  python3 tools/build_streets.py              # rebuild from the cached tiles in tools/.street_cache/

Run it locally now and then (streets rarely change). The weekly routine does not run it. Coverage: all of Lakewood,
plus the streets within 0.9 mile of each place on the site's map that lies outside Lakewood (the Jewish
neighbourhoods of Jackson, Howell, Toms River, Manchester, ...). Add a place to places.json and rebuild to cover it.

Data: (c) OpenStreetMap contributors, ODbL (the page credits them). One Overpass request per map tile; only
street names and shapes are requested - nothing about visitors or the site's owner is sent.

Output streets.json:
  {"source": ..., "base": [lat0, lng0], "unit": 0.0001, "towns": ["Lakewood", "Jackson", ...],
   "streets": [["Ocean Avenue", 0, [[dlat, dlng, dlat, dlng, ...], ...]], ...]}   # [name, index into towns, paths]
  Every path is a flat list of integers in `unit` degrees (11 m): the first point as an offset from `base`,
  then each next point as a step from the one before, so a street is a few dozen small numbers. `p` has one path per piece of the street; the same name in two places (Central Avenue in
  Lakewood and in Jackson) is two entries.
"""
import argparse
import json
import math
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = pathlib.Path(__file__).resolve().parent / ".street_cache"
OUT = ROOT / "streets.json"

# Lakewood and the surrounding areas people rent in: Jackson, Howell, Toms River, Manchester, Brick.
SOUTH, NORTH, WEST, EAST = 39.94, 40.21, -74.40, -74.08
TILE_LAT, TILE_LNG = 0.045, 0.08
UNIT = 1e-4
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter",
           "https://z.overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = "lakewood-rentals-streets/1.0 (open-source rental list)"
HIGHWAYS = "residential|tertiary|secondary|primary|trunk|unclassified|living_street|primary_link|secondary_link|tertiary_link"

CENTER = (40.0979, -74.2179)
# All of Lakewood Township is covered. In the surrounding towns only the neighbourhoods the site has places for
# (every pin in places.json that lies outside Lakewood) are covered: streets within NEAR_MILES of one of those pins.
NEAR_MILES = 0.9
BOUNDARY_TOWNS = ["Lakewood", "Jackson", "Howell", "Manchester", "Brick"]   # Toms River's border is the fallback

# Rough town centres, only used to label which town a street is in (so two "Central Avenue"s can be told apart).
TOWNS = {"Lakewood": (40.0979, -74.2179), "Jackson": (40.1000, -74.3550), "Howell": (40.1500, -74.1900),
         "Toms River": (39.9800, -74.2000), "Manchester": (39.9800, -74.3400), "Brick": (40.0600, -74.1100)}


def miles(lat1, lng1, lat2, lng2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def tiles():
    out, s = [], SOUTH
    while s < NORTH - 1e-9:
        w = WEST
        while w < EAST - 1e-9:
            out.append((round(s, 4), round(w, 4), round(min(s + TILE_LAT, NORTH), 4), round(min(w + TILE_LNG, EAST), 4)))
            w += TILE_LNG
        s += TILE_LAT
    return out


def fetch_tile(s, w, n, e):
    q = (f'[out:json][timeout:90];way["highway"~"^({HIGHWAYS})$"]["name"]({s},{w},{n},{e});out geom tags;')
    last = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
            return json.loads(urllib.request.urlopen(req, timeout=180).read())["elements"]
        except Exception as ex:  # noqa: BLE001 - try the next mirror
            last = ex
    raise RuntimeError(last)


def fetch_boundaries():
    fn = CACHE / "boundaries.json"
    if fn.exists():
        return
    q = ('[out:json][timeout:120];rel["boundary"="administrative"]["admin_level"="8"]'
         f'["name"~"^({"|".join(BOUNDARY_TOWNS)}) Township$"]({SOUTH - 0.1},{WEST - 0.1},{NORTH + 0.1},{EAST + 0.1});out geom;')
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
            fn.write_bytes(urllib.request.urlopen(req, timeout=180).read())
            print("town borders downloaded", flush=True)
            return
        except Exception as ex:  # noqa: BLE001
            print(f"town borders failed on {url.split('/')[2]}: {str(ex)[:80]}", flush=True)


def fetch_routes():
    """State and US routes of every road class (Route 70 is a freeway-type road the street query skips)."""
    fn = CACHE / "routes.json"
    if fn.exists():
        return
    q = (f'[out:json][timeout:120];way["highway"]["ref"~"^(NJ|US) "]({SOUTH},{WEST},{NORTH},{EAST});out geom tags;')
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
            fn.write_bytes(urllib.request.urlopen(req, timeout=180).read())
            print("state routes downloaded", flush=True)
            return
        except Exception as ex:  # noqa: BLE001
            print(f"state routes failed on {url.split('/')[2]}: {str(ex)[:80]}", flush=True)


def fetch_all():
    CACHE.mkdir(exist_ok=True)
    fetch_boundaries()
    fetch_routes()
    for i, t in enumerate(tiles()):
        fn = CACHE / f"tile_{i:02d}.json"
        if fn.exists():
            continue
        for attempt in range(4):
            try:
                els = fetch_tile(*t)
                fn.write_text(json.dumps({"bbox": t, "elements": els}))
                print(f"tile {i + 1}: {len(els)} ways", flush=True)
                break
            except Exception as ex:  # noqa: BLE001
                print(f"tile {i + 1} attempt {attempt + 1} failed: {str(ex)[:100]}", flush=True)
                time.sleep(20)
        time.sleep(3)                                   # be polite to the public server


# ---- geometry ----------------------------------------------------------------------------------

def _perp(p, a, b):
    """Distance in metres from p to segment a-b (flat approximation, fine at this scale)."""
    k = 111320.0
    cx = math.cos(math.radians(a[0]))
    ax, ay, bx, by, px, py = a[1] * k * cx, a[0] * k, b[1] * k * cx, b[0] * k, p[1] * k * cx, p[0] * k
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def simplify(pts, tol_m=30.0):
    """Douglas-Peucker; always keeps both ends (ends are where streets cross, so intersections stay exact)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        far, fd = None, 0.0
        for k in range(i + 1, j):
            d = _perp(pts[k], pts[i], pts[j])
            if d > fd:
                far, fd = k, d
        if far is not None and fd > tol_m:
            keep[far] = True
            stack += [(i, far), (far, j)]
    return [p for p, k in zip(pts, keep) if k]


def route_names(tags):
    """'NJ 88' / 'US 9' / 'NJ 70' -> 'Route 88' etc., so people can search "Route 88"."""
    out = []
    for ref in re.split(r"[;,]", tags.get("ref", "")):
        m = re.fullmatch(r"\s*(?:NJ|US)\s+(\d{1,3})\s*", ref)
        if m:
            out.append(f"Route {m.group(1)}")
    return out


def cluster(ways, link_miles=0.3):
    """Split same-named ways into separate streets (same name in different towns): single linkage."""
    n = len(ways)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            close = any(miles(a[0], a[1], b[0], b[1]) <= link_miles for a in ways[i] for b in ways[j])
            if close:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(ways[i])
    return list(groups.values())


def street_town(paths):
    """The town a street belongs to, from the real borders: Lakewood if at least LAKEWOOD_MIN_MILES of it is inside
    Lakewood (Vermont Avenue and Route 88 start there and run on), otherwise the town holding most of its length.
    (Labelling by the point nearest Lakewood put Jackson's Bartley Road in Lakewood.)"""
    length = {}
    for p in paths:
        for a, b in zip(p, p[1:]):
            seg = miles(a[0], a[1], b[0], b[1])
            n = max(1, math.ceil(seg / 0.05))                      # test every 0.05 mile: one long segment can cross a border
            for k in range(n):
                f = (k + 0.5) / n
                town = town_of(a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
                length[town] = length.get(town, 0.0) + seg / n
    if not length:
        return town_of(*paths[0][0])
    if length.get("Lakewood", 0.0) >= LAKEWOOD_MIN_MILES:
        return "Lakewood"
    return max(length, key=length.get)


def join_paths(paths):
    """Chain pieces of a street that share an end point into longer lines (fewer points, smoother lines)."""
    paths = [list(p) for p in paths]
    changed = True
    while changed:
        changed = False
        for i in range(len(paths)):
            for j in range(len(paths)):
                if i == j or not paths[i] or not paths[j]:
                    continue
                a, b = paths[i], paths[j]
                if a[-1] == b[0]:
                    paths[i] = a + b[1:]
                elif a[-1] == b[-1]:
                    paths[i] = a + b[::-1][1:]
                elif a[0] == b[0]:
                    paths[i] = a[::-1] + b[1:]
                elif a[0] == b[-1]:
                    paths[i] = b + a[1:]
                else:
                    continue
                paths[j] = []
                changed = True
    return [p for p in paths if p]


# ---- town borders ---------------------------------------------------------------------------------

def _chain(ways):
    """Join the boundary pieces of a relation (lists of (lat, lng)) end to end into closed rings."""
    ways = [list(w) for w in ways if len(w) > 1]
    rings = []
    while ways:
        ring = ways.pop(0)
        grew = True
        while grew and ring[0] != ring[-1]:
            grew = False
            for i, w in enumerate(ways):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                ways.pop(i)
                grew = True
                break
        rings.append(ring)
    return rings


BORDERS_FILE = ROOT / "data" / "town_borders.json"
BORDER_TOLERANCE_M = 20.0            # how much the saved borders are simplified (the fewer metres, the truer the label)
LAKEWOOD_MIN_MILES = 0.4             # a street with this much of it inside Lakewood counts as a Lakewood street


def load_boundaries(cache=None):
    """{'Lakewood': [ring, ...], ...}. Uses the checked-in data/town_borders.json; if it is missing, builds it from
    the downloaded boundaries.json in the tile cache (simplified to ~20 m)."""
    if BORDERS_FILE.exists():
        return {k: [[tuple(p) for p in ring] for ring in rings] for k, rings in json.loads(BORDERS_FILE.read_text()).items()}
    f = (cache or CACHE) / "boundaries.json"
    if not f.exists():
        return {}
    out = {}
    for rel in json.loads(f.read_text())["elements"]:
        name = rel.get("tags", {}).get("name", "").replace(" Township", "")
        ways = [[(g["lat"], g["lon"]) for g in m["geometry"]] for m in rel.get("members", [])
                if m.get("role") == "outer" and m.get("geometry")]
        if name in BOUNDARY_TOWNS and ways:
            out[name] = [simplify(r, BORDER_TOLERANCE_M) for r in _chain(ways)]
    BORDERS_FILE.parent.mkdir(exist_ok=True)
    BORDERS_FILE.write_text(json.dumps({k: [[[round(a, 5), round(b, 5)] for a, b in r] for r in rings]
                                        for k, rings in out.items()}, separators=(",", ":")))
    return out


def inside(lat, lng, rings):
    """Ray casting: is the point inside any of the rings?"""
    for ring in rings:
        hit = False
        j = len(ring) - 1
        for i in range(len(ring)):
            (la1, ln1), (la2, ln2) = ring[i], ring[j]
            if (ln1 > lng) != (ln2 > lng) and lat < (la2 - la1) * (lng - ln1) / (ln2 - ln1) + la1:
                hit = not hit
            j = i
        if hit:
            return True
    return False


BOUNDARIES = {}


def town_of(lat, lng):
    """The town a point is in: by the real border where we have it, else the nearest town centre."""
    for name in BOUNDARY_TOWNS:
        if name in BOUNDARIES and inside(lat, lng, BOUNDARIES[name]):
            return name
    return min(TOWNS, key=lambda t: miles(lat, lng, *TOWNS[t]))


def encode(points):
    """[lat0, lng0, dlat, dlng, ...]: the first point as an offset from the box corner, then small steps."""
    out, prev = [], (0, 0)
    for p in points:
        cur = (round((p[0] - SOUTH) / UNIT), round((p[1] - WEST) / UNIT))
        out += [cur[0] - prev[0], cur[1] - prev[1]]
        prev = cur
    return out


def decode(flat):
    """Inverse of encode: -> [(lat, lng), ...]."""
    pts, la, ln = [], 0, 0
    for i in range(0, len(flat) - 1, 2):
        la, ln = la + flat[i], ln + flat[i + 1]
        pts.append((SOUTH + la * UNIT, WEST + ln * UNIT))
    return pts


def neighbourhood_pins(places_file):
    """Pins of the neighbourhoods the site knows outside Lakewood (the Jewish neighbourhoods of the surrounding towns)."""
    pins = []
    towns_level = {"jackson", "howell", "lakewood", "toms river", "manchester", "brick", "freehold"}
    for key, e in json.loads(pathlib.Path(places_file).read_text()).items():
        if e.get("lat") is None or key in towns_level:
            continue
        if town_of(e["lat"], e["lng"]) != "Lakewood":
            pins.append((e["lat"], e["lng"]))
    return pins


def build(places_file=None):
    global BOUNDARIES
    BOUNDARIES = load_boundaries()
    if not BOUNDARIES:
        print("WARNING: no town borders cached; towns are guessed from the nearest centre (run with --fetch)")
    pins = neighbourhood_pins(places_file or ROOT / "places.json")
    ways = {}
    files = sorted(CACHE.glob("tile_*.json"))
    if not files:
        sys.exit("no cached tiles: run with --fetch first")
    extra = [CACHE / "routes.json"] if (CACHE / "routes.json").exists() else []
    if not extra:
        print("WARNING: no routes.json cached (Route 70 will be missing); run with --fetch")
    for f in files + extra:
        for el in json.loads(f.read_text())["elements"]:
            if el.get("type") != "way" or not el.get("geometry"):
                continue
            ways[el["id"]] = el
    by_name = {}
    for el in ways.values():
        tags = el.get("tags", {})
        pts = [(g["lat"], g["lon"]) for g in el["geometry"]]
        for name in ([tags["name"]] if tags.get("name") else []) + route_names(tags):     # NJ 70 has a ref but no name
            by_name.setdefault(name.strip(), []).append(simplify(pts))
    merged = {}
    for name, ws in sorted(by_name.items()):
        for grp in cluster(ws):
            allpts = [p for w in grp for p in w]
            town = street_town(join_paths(grp))
            if town != "Lakewood":
                # outside Lakewood: only the streets of the neighbourhoods the site covers
                if not any(miles(p[0], p[1], la, ln) <= NEAR_MILES for p in allpts for la, ln in pins):
                    continue
            merged.setdefault((name, town), []).extend(join_paths(grp))
    streets = []
    for (name, town), paths in sorted(merged.items()):
        streets.append([name, list(TOWNS).index(town), [encode(p) for p in join_paths(paths)]])
    data = {"source": "OpenStreetMap contributors (ODbL)", "base": [SOUTH, WEST], "unit": UNIT,
            "towns": list(TOWNS), "streets": streets}
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    npts = sum(len(p) // 2 for s in streets for p in s[2])
    print(f"{len(streets)} streets, {npts} points, {OUT.stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download tiles first")
    ap.add_argument("--cache", help="folder with tile_*.json and boundaries.json (default tools/.street_cache)")
    ap.add_argument("--places", help="places.json whose pins say which neighbourhoods outside Lakewood to cover")
    args = ap.parse_args()
    if args.cache:
        CACHE = pathlib.Path(args.cache)
    if args.fetch:
        fetch_all()
    build(args.places)
