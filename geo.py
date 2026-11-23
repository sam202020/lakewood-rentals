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
           "sholom": "shalom", "lutsk": "lutzk"}


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
    # "Lutzk near Westgate" is at Lutzk; Westgate only says roughly where, so it is not averaged in.
    pre = re.split(r"\s+near\s+", location or "", maxsplit=1, flags=re.I)
    if len(pre) == 2 and pre[0].strip():
        left = location_parts(pre[0])
        if left and all(_known(places, k) for k in left):
            parts = left
            location = pre[0]
    # A whole-name entry wins, and an intersection matches in either order
    # ("Sunset & James" == "James & Sunset").
    cands = [normalize(location)]
    if len(parts) == 2:
        cands += [" ".join(parts), " ".join(reversed(parts))]
    whole = next((e for e in (_known(places, c) for c in cands) if e), None)
    if whole:
        town = normalize(location) in TOWNS
        return {"lat": whole["lat"], "lng": whole["lng"], "precision": "town" if town else "place", "unknown": [], "spread": 0,
                "unverified": [] if town or whole.get("source") != "osm" else [normalize(location)]}

    keys = parts
    found = [(k, _known(places, k)) for k in keys]
    unknown = [k for k, e in found if e is None and k not in places]
    hits = [(k, e) for k, e in found if e]
    specific = [(k, e) for k, e in hits if k not in TOWNS]
    use = specific or hits
    if not use:
        return {"lat": None, "lng": None, "precision": None, "unknown": unknown, "unverified": [], "spread": 0}
    lat = sum(e["lat"] for _, e in use) / len(use)
    lng = sum(e["lng"] for _, e in use) / len(use)
    spread = max((haversine_miles(a["lat"], a["lng"], b["lat"], b["lng"])
                  for i, (_, a) in enumerate(use) for _, b in use[i + 1:]), default=0)
    return {"lat": round(lat, 5), "lng": round(lng, 5),
            "precision": "place" if specific else "town", "unknown": unknown,
            "spread": round(spread, 1),     # miles between the places this pin is the average of
            # still resting on a raw OpenStreetMap pin that nobody has checked on Google Maps
            "unverified": [k for k, e in use if e.get("source") == "osm" and k not in TOWNS]}


def plausible(lat, lng):
    return haversine_miles(lat, lng, *LAKEWOOD) <= MAX_MILES_FROM_LAKEWOOD


# ---- names shown in the "Near" drop-down ------------------------------------
_SUFFIX = {"st": "Street", "ave": "Avenue", "rd": "Road", "ln": "Lane", "dr": "Drive", "ct": "Court",
           "blvd": "Boulevard", "pl": "Place", "pt": "Point", "pkwy": "Parkway"}
_SMALL = {"at", "of", "the", "and", "in", "on"}
_ORDINAL_ONLY = re.compile(r"(?:[NSEW]\.? )?\d+(?:st|nd|rd|th)", re.I)
_STREET_WORDS = set(_SUFFIX.values())


def display_name(key, entry):
    """Tidy label for the drop-down: '13Th' -> '13th Street', 'Cherry St' -> 'Cherry Street',
    'Rt 70' -> 'Route 70', 'Club At Jackson 21' -> 'Club at Jackson 21'.
    An entry may set "label" to override the raw name."""
    name = (entry.get("label") or entry.get("name") or key.title()).strip()
    name = re.sub(r"\b(\d+)(st|nd|rd|th)\b", lambda m: m.group(1) + m.group(2).lower(), name, flags=re.I)
    if _ORDINAL_ONLY.fullmatch(name):
        name += " Street"
    out = []
    words = name.split(" ")
    for i, w in enumerate(words):
        bare = w.rstrip(".,").lower()
        tail = w[len(w.rstrip(".,")):]
        nxt = words[i + 1] if i + 1 < len(words) else None
        if i == 0 and bare in ("rt", "rte"):
            out.append("Route" + tail)
        elif i > 0 and bare in _SUFFIX and (nxt is None or nxt in ("&", "/")):
            out.append(_SUFFIX[bare] + tail)
        elif i > 0 and bare in _SMALL:
            out.append(bare + tail)
        else:
            out.append(w)
    return " ".join(out)


def _base(name):
    """'Clover Street' -> 'clover', 'Ocean Avenue (Route 88)' -> 'ocean', for matching a part to a place."""
    n = re.sub(r"\(.*?\)", " ", name.lower())
    words = [w for w in re.sub(r"[^a-z0-9+ ]", " ", n).split() if w not in {x.lower() for x in _STREET_WORDS}]
    return " ".join(words)


_ADDRESS = re.compile(r"^\d{1,5}[A-Za-z]?\s+(?:[NSEW]\.?\s+)?[A-Za-z]")


def looks_like_address(text):
    """True for '957 W. County Ln.' or '22 Enclave Blvd', not for '13th & Princeton', '55+Community' or 'Jackson 21'."""
    return bool(_ADDRESS.match(str(text or "").strip()))


def picker_entries(places, merge_miles=0.15, intersection_miles=0.25):
    """One entry per place name people would recognise, for the "Near" drop-down.

    Street addresses are never offered. Names are tidied (display_name), exact duplicates are merged (manual beats OSM),
    and a bare street name is merged into its suffixed twin ("James" + "James Street")
    when they sit within `merge_miles` of each other. Places whose twin is somewhere
    else are left alone, because they may be genuinely different.
    """
    best = {}
    for k, e in places.items():
        if e.get("lat") is None or e.get("hide"):
            continue
        name = display_name(k, e)
        if looks_like_address(name):      # an address is not a neighbourhood: never offer it
            continue
        cur = best.get(name.lower())
        if cur is None or (e.get("source") == "manual" and cur["source"] != "manual"):
            best[name.lower()] = {"name": name, "lat": e["lat"], "lng": e["lng"], "source": e.get("source"),
                                  "aka": e.get("aka")}
    for low, item in list(best.items()):
        for suffix in _STREET_WORDS:
            twin = best.get(low + " " + suffix.lower())
            if twin and haversine_miles(item["lat"], item["lng"], twin["lat"], twin["lng"]) <= merge_miles:
                best.pop(low, None)
                break
    # An intersection ("13th Street & Princeton Avenue", "Route 88 & Clover") that sits on top of a place named
    # after one of its parts ("13th Street", "Clover") is the same neighbourhood: keep the simple name only.
    by_base = {}
    for item in best.values():
        by_base.setdefault(_base(item["name"]), item)
    for low, item in list(best.items()):
        parts = [_base(x) for x in re.split(r"\s+[&/]\s+", item["name"])]
        if len(parts) < 2:
            continue
        for part in parts:
            twin = by_base.get(part)
            if twin and twin is not item and haversine_miles(item["lat"], item["lng"], twin["lat"], twin["lng"]) <= intersection_miles:
                best.pop(low, None)
                break
    out = []
    for v in best.values():
        item = {"name": v["name"], "lat": v["lat"], "lng": v["lng"]}
        if v.get("aka"):
            item["aka"] = v["aka"]          # other spellings people type ("Lutsk" for "Lutzk")
        out.append(item)
    return sorted(out, key=lambda v: v["name"].lower())


# ---- streets (streets.json, built by tools/build_streets.py) --------------------------------------

def _street_points(data, street):
    b, u = data["base"], data["unit"]
    return [(b[0] + path[i] * u, b[1] + path[i + 1] * u) for path in street["p"] for i in range(0, len(path) - 1, 2)]


def streets_for_page(data, picker, near_miles=0.6):
    """-> (streets_data, picker) ready to embed in the page.

    * a street that has the same name as a neighbourhood the owner defined, and lies within `near_miles` of it,
      is dropped: the owner's neighbourhood wins ("Clover" is a place, not just Clover Street)
    * the old point-only "Route 88" style entries are dropped when the street data has that route as a line
    """
    if not data or not data.get("streets"):
        return None, picker
    names = {_base(p["name"]): p for p in picker if not p["name"].lower().startswith("route ")}
    keep = []
    for s in data["streets"]:
        place = names.get(_base(s["n"]))
        if place and any(haversine_miles(place["lat"], place["lng"], la, ln) <= near_miles
                         for la, ln in _street_points(data, s)):
            continue
        keep.append(s)
    routes = {s["n"].lower() for s in keep if s["n"].lower().startswith("route ")}
    picker = [p for p in picker if p["name"].lower() not in routes]
    out = dict(data)
    out["streets"] = keep
    return out, picker
