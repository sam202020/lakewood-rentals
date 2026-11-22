"""Turn the PDF's location text into map coordinates.

Locations are neighbourhoods and streets ("Raintree", "Sunset & James",
"Brook / Ridge / E. 7th"), not addresses, so a listing gets the centre of the
place(s) it names - good for "closest to me", not for a rooftop pin.

Coordinates live in places.json (human-editable, checked in):

    "raintree": {"name": "Raintree", "lat": 40.09, "lng": -74.19,
                 "source": "osm" | "manual" | "unresolved", ...}

* tools/geocode_places.py fills in OpenStreetMap results for new names
  (run locally; never overwrites source == "manual").
* To fix or add a place by hand, set lat/lng and "source": "manual".
* build.py attaches lat/lng to each listing via resolve() below. Names missing
  from the table are reported as warnings by checks.py.
"""
import json
import math
import pathlib
import re

PLACES_FILE = pathlib.Path(__file__).parent / "places.json"

# Town-level names: a poor guide to where in town a listing is, so they are
# ignored when a more specific part of the same location resolves.
TOWNS = {"lakewood", "jackson", "toms river", "howell", "manchester", "brick", "freehold"}

# Rough centre of Lakewood, NJ - used to sanity-check geocoder results.
LAKEWOOD = (40.0979, -74.2179)
MAX_MILES_FROM_LAKEWOOD = 20


# Misspellings / short forms in the PDF that should resolve like the real name.
ALIASES = {"jacksn": "jackson", "jksn": "jackson", "hwl": "howell", "prospct": "prospect",
           "somerst": "somerset", "hearthstn": "hearthstone", "brookwd": "brookwood",
           "sholom": "shalom"}


def normalize(part):
    """Lower-case key for a place name: punctuation, 'area', 'near', 'off' removed."""
    s = part.lower()
    s = re.sub(r"\b(area|near|off)\b", " ", s)
    s = re.sub(r"[^a-z0-9+ ]", " ", s)
    s = " ".join(ALIASES.get(t, t) for t in s.split())
    return s.strip()


def location_parts(location):
    """Split 'Sunset / James Area' or 'Holly Oaks, Manchester' into place names."""
    parts = re.split(r"\s*/\s*|,\s*|\s+&\s+|\s+near\s+", location or "", flags=re.I)
    out = []
    for p in parts:
        k = normalize(p)
        if k and k not in out:
            out.append(k)
    return out


def haversine_miles(lat1, lng1, lat2, lng2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_EXPAND = {"st": "street", "ave": "avenue", "rd": "road", "ct": "court", "ln": "lane", "dr": "drive",
           "pt": "point", "blvd": "boulevard", "mass": "massachusetts avenue", "hwl": "howell",
           "jksn": "jackson", "jacksn": "jackson", "prospct": "prospect", "somerst": "somerset",
           "hearthstn": "hearthstone", "brookwd": "brookwood", "centrl": "central", "lkwd": "lakewood",
           "w": "west", "n": "north", "e": "east", "s": "south"}


def expand_abbreviations(key):
    """'heritage pt' -> 'heritage point', 'mass' -> 'massachusetts avenue' (for geocoder queries)."""
    return " ".join(_EXPAND.get(t, t) for t in key.split())


def load_places(path=PLACES_FILE):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return {}


def _known(places, key):
    e = places.get(key)
    return e if e and e.get("lat") is not None and e.get("lng") is not None else None


def resolve(location, places):
    """-> dict(lat, lng, precision, unknown) for a location string.

    precision: "place" (a named street/neighbourhood), "town" (town-level only)
    or None (nothing resolved). `unknown` lists the parts missing from `places`.
    """
    parts = location_parts(location)
    # A whole-name entry wins, and an intersection matches in either order
    # ("Sunset & James" == "James & Sunset").
    cands = [normalize(location)]
    if len(parts) == 2:
        cands += [" ".join(parts), " ".join(reversed(parts))]
    whole = next((e for e in (_known(places, c) for c in cands) if e), None)
    if whole:
        return {"lat": whole["lat"], "lng": whole["lng"],
                "precision": "town" if normalize(location) in TOWNS else "place", "unknown": []}

    keys = parts
    found = [(k, _known(places, k)) for k in keys]
    unknown = [k for k, e in found if e is None and k not in places]
    hits = [(k, e) for k, e in found if e]
    specific = [(k, e) for k, e in hits if k not in TOWNS]
    use = specific or hits
    if not use:
        return {"lat": None, "lng": None, "precision": None, "unknown": unknown}
    lat = sum(e["lat"] for _, e in use) / len(use)
    lng = sum(e["lng"] for _, e in use) / len(use)
    return {"lat": round(lat, 5), "lng": round(lng, 5),
            "precision": "place" if specific else "town", "unknown": unknown}


def plausible(lat, lng):
    return haversine_miles(lat, lng, *LAKEWOOD) <= MAX_MILES_FROM_LAKEWOOD
