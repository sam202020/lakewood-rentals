"""Which town a point is in, from the real municipal borders (data/town_borders.json, from OpenStreetMap).

Used for the town shown next to every street and every neighbourhood in the search suggestions, and by
tools/build_streets.py. Points outside the borders we have (the rest of Toms River, ...) take the nearest
town centre.
"""
import functools
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
BORDERS_FILE = ROOT / "data" / "town_borders.json"
BOUNDARY_TOWNS = ["Lakewood", "Jackson", "Howell", "Manchester", "Brick"]      # Toms River's border is the fallback
# Rough town centres, only a fallback for points outside the borders above.
TOWN_CENTERS = {"Lakewood": (40.0979, -74.2179), "Jackson": (40.1000, -74.3550), "Howell": (40.1500, -74.1900),
                "Toms River": (39.9800, -74.2000), "Manchester": (39.9800, -74.3400), "Brick": (40.0600, -74.1100)}


def _miles(lat1, lng1, lat2, lng2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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


@functools.lru_cache(maxsize=1)
def borders():
    """{'Lakewood': [ring, ...], ...} with rings of (lat, lng); {} if the file is missing."""
    try:
        raw = json.loads(BORDERS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return {k: [[tuple(p) for p in ring] for ring in rings] for k, rings in raw.items()}


def town_of(lat, lng, border_set=None):
    """'Lakewood', 'Jackson', 'Howell', 'Manchester', 'Brick' or (by the nearest centre) 'Toms River'."""
    b = borders() if border_set is None else border_set
    for name in BOUNDARY_TOWNS:
        if name in b and inside(lat, lng, b[name]):
            return name
    return min(TOWN_CENTERS, key=lambda t: _miles(lat, lng, *TOWN_CENTERS[t]))
