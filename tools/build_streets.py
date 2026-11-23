#!/usr/bin/env python3
"""Build streets.json: every named street around Lakewood, as simplified lines, for "sort by nearest this street".

  python3 tools/build_streets.py --fetch      # download from OpenStreetMap (Overpass), then build
  python3 tools/build_streets.py              # rebuild from the cached tiles in tools/.street_cache/

Run it locally now and then (streets rarely change). The weekly routine does not run it.

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

# Streets whose middle is farther than this from the centre of Lakewood are left out (woods, far Brick and Toms River).
MAX_MILES = 9.5
CENTER = (40.0979, -74.2179)

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


def fetch_all():
    CACHE.mkdir(exist_ok=True)
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


def town_of(lat, lng):
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


def build():
    ways = {}
    files = sorted(CACHE.glob("tile_*.json"))
    if not files:
        sys.exit("no cached tiles: run with --fetch first")
    for f in files:
        for el in json.loads(f.read_text())["elements"]:
            if el.get("type") != "way" or not el.get("geometry"):
                continue
            ways[el["id"]] = el
    by_name = {}
    for el in ways.values():
        tags = el.get("tags", {})
        pts = [(g["lat"], g["lon"]) for g in el["geometry"]]
        for name in [tags["name"]] + route_names(tags):
            by_name.setdefault(name.strip(), []).append(simplify(pts))
    merged = {}
    for name, ws in sorted(by_name.items()):
        for grp in cluster(ws):
            allpts = [p for w in grp for p in w]
            lat = sum(p[0] for p in allpts) / len(allpts)
            lng = sum(p[1] for p in allpts) / len(allpts)
            if miles(lat, lng, *CENTER) > MAX_MILES:
                continue
            # label the town by the part of the street nearest Lakewood ("Route 88" runs through several towns)
            nearest = min(allpts, key=lambda p: miles(p[0], p[1], *CENTER))
            key = (name, town_of(*nearest))
            merged.setdefault(key, []).extend(join_paths(grp))
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
    ap.add_argument("--cache", help="folder with tile_*.json (default tools/.street_cache)")
    args = ap.parse_args()
    if args.cache:
        CACHE = pathlib.Path(args.cache)
    if args.fetch:
        fetch_all()
    build()
