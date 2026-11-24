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

import towns

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


_DIRECTIONS = {"e": "east", "w": "west", "n": "north", "s": "south"}


def _base(name):
    """'Clover Street' -> 'clover', 'Ocean Avenue (Route 88)' -> 'ocean', 'E 7th Street' -> 'east 7th'
    (a street's own name, for telling when two lists mean the same place)."""
    n = re.sub(r"\(.*?\)", " ", name.lower())
    drop = {x.lower() for x in _STREET_WORDS}
    words = [_DIRECTIONS.get(w, w) for w in re.sub(r"[^a-z0-9+ ]", " ", n).split() if w not in drop]
    return " ".join(words)


_ADDRESS = re.compile(r"^\d{1,5}[A-Za-z]?\s+(?:[NSEW]\.?\s+)?[A-Za-z]")


def looks_like_address(text):
    """True for '957 W. County Ln.' or '22 Enclave Blvd', not for '13th & Princeton', '55+Community' or 'Jackson 21'."""
    return bool(_ADDRESS.match(str(text or "").strip()))


def strip_town(name, town):
    """'Harmony Hills, Jackson' -> 'Harmony Hills' (the town is shown next to the name instead);
    'Mackenzie Toms River' -> 'Mackenzie'. Only when something is left, and only the place's own town."""
    out = re.sub(r",?\s+" + re.escape(town) + r"$", "", name, flags=re.I).strip(" ,")
    return out if out and out.lower() != name.lower() and len(out) >= 3 else name


TOWN_NAMES = {"lakewood", "jackson", "howell", "toms river", "manchester", "brick"}


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
        town = towns.town_of(e["lat"], e["lng"])
        key = (name.lower(), town)                  # the same name in two towns is two places
        cur = best.get(key)
        if cur is None or (e.get("source") == "manual" and cur["source"] != "manual"):
            best[key] = {"name": name, "lat": e["lat"], "lng": e["lng"], "source": e.get("source"),
                         "aka": e.get("aka"), "town": town}
    for (low, town), item in list(best.items()):
        for suffix in _STREET_WORDS:
            twin = best.get((low + " " + suffix.lower(), town))
            if twin and haversine_miles(item["lat"], item["lng"], twin["lat"], twin["lng"]) <= merge_miles:
                best.pop((low, town), None)
                break
    # An intersection ("13th Street & Princeton Avenue", "Route 88 & Clover") that sits on top of a place named
    # after one of its parts ("13th Street", "Clover") is the same neighbourhood: keep the simple name only.
    by_base = {}
    for item in best.values():
        by_base.setdefault(_base(item["name"]), item)
    for key, item in list(best.items()):
        parts = [_base(x) for x in re.split(r"\s+[&/]\s+", item["name"])]
        if len(parts) < 2:
            continue
        for part in parts:
            twin = by_base.get(part)
            if twin and twin is not item and haversine_miles(item["lat"], item["lng"], twin["lat"], twin["lng"]) <= intersection_miles:
                best.pop(key, None)
                break
    out = []
    for v in best.values():
        town = v["town"]
        # a town is not "in" itself: "Jackson" gets no town; "Harmony Hills, Jackson" becomes "Harmony Hills" + Jackson
        name = v["name"] if v["name"].lower() in TOWN_NAMES else strip_town(v["name"], town)
        item = {"name": name, "lat": v["lat"], "lng": v["lng"]}
        if v["name"].lower() not in TOWN_NAMES:
            item["town"] = town
        if v.get("aka"):
            item["aka"] = v["aka"]          # other spellings people type ("Lutsk" for "Lutzk")
        out.append(item)
    return sorted(out, key=lambda v: (v["name"].lower(), v.get("town", "")))


# ---- streets (streets.json, built by tools/build_streets.py) --------------------------------------

def _street_points(data, street):
    """Absolute (lat, lng) vertices of a [name, town_index, paths] street (paths are delta-encoded)."""
    b, u = data["base"], data["unit"]
    pts = []
    for flat in street[2]:
        la = ln = 0
        for i in range(0, len(flat) - 1, 2):
            la, ln = la + flat[i], ln + flat[i + 1]
            pts.append((b[0] + la * u, b[1] + ln * u))
    return pts


def streets_for_page(data, picker, near_miles=0.6):
    """-> (streets_data, picker) ready to embed in the page.

    * a street that has the same name as a neighbourhood the owner defined, and lies within `near_miles` of it,
      is flagged as a duplicate (4th item = 1): the owner's neighbourhood wins in the suggestions ("Clover" is a
      place, not just Clover Street), but the street's lines still serve intersections ("Clover & Ocean")
    * the old point-only "Route 88" style entries are dropped when the street data has that route as a line
    """
    if not data or not data.get("streets"):
        return None, picker
    names = {_base(p["name"]): p for p in picker if not p["name"].lower().startswith("route ")}
    keep = []
    for s in data["streets"]:
        place = names.get(_base(s[0]))
        dup = bool(place and any(haversine_miles(place["lat"], place["lng"], la, ln) <= near_miles
                                 for la, ln in _street_points(data, s)))
        # a duplicate of an owner-defined neighbourhood is kept (flag 1) so intersections can still use its
        # lines, but it is not offered as a separate suggestion
        keep.append(list(s[:3]) + [1] if dup else list(s[:3]))
    routes = {s[0].lower() for s in keep if s[0].lower().startswith("route ")}
    picker = [p for p in picker if p["name"].lower() not in routes]
    out = dict(data)
    out["streets"] = keep
    return out, picker


def miles_to_street(data, street, lat, lng):
    """Shortest distance in miles from a point to the street's lines (flat-earth maths, fine over a few miles)."""
    b, u = data["base"], data["unit"]
    kx, ky = math.cos(math.radians(lat)) * 69.172, 69.0
    best = float("inf")
    for flat in street[2]:
        la = ln = 0
        prev = None
        for i in range(0, len(flat) - 1, 2):
            la, ln = la + flat[i], ln + flat[i + 1]
            cur = ((b[1] + ln * u - lng) * kx, (b[0] + la * u - lat) * ky)
            if prev is not None:
                dx, dy = cur[0] - prev[0], cur[1] - prev[1]
                L2 = dx * dx + dy * dy
                t = max(0, min(1, -(prev[0] * dx + prev[1] * dy) / L2)) if L2 else 0
                best = min(best, math.hypot(prev[0] + t * dx, prev[1] + t * dy))
            best = min(best, math.hypot(*cur))
            prev = cur
    return best


SHULS_FILE = pathlib.Path(__file__).parent / "shuls.json"


def spoken_shul_name(name):
    """Nobody in Lakewood says "Congregation": "Congregation Kol Aryeh" -> "Kol Aryeh", "Cong. Belz Meadows" -> "Belz Meadows"."""
    n = re.sub(r"\bcong(?:regation|regations)?\b\.?\s*", "", name, flags=re.I)
    n = re.sub(r"^(?:of|the)\s+(?=\S)", "", n.strip(), flags=re.I) if n != name else n
    n = re.sub(r"\s{2,}", " ", n).strip(" -,/")
    n = re.sub(r"^/\s*", "", n)
    return n or name


def load_shuls(path=SHULS_FILE):
    """Shuls for the page's "Near" search: dicts with name (as spoken), lat, lng, town, address, aka, area; Lakewood first.

    shuls.json is harvested from Google Maps (see CLAUDE.md); "hide": true drops an entry; "area" names the
    place (places.json display name) that is the same place, so the drop-down shows it once (merge_shuls).
    """
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return []
    out = []
    for s in data.get("shuls", []):
        if s.get("hide") or s.get("lat") is None or s.get("lng") is None:
            continue
        town = s.get("town") or towns.town_of(s["lat"], s["lng"])
        out.append({"name": spoken_shul_name(s["name"]), "lat": round(s["lat"], 5), "lng": round(s["lng"], 5), "town": town,
                    "address": s.get("address", ""), "aka": s.get("aka", []), "area": s.get("area")})
    out.sort(key=lambda s: (s["town"] != "Lakewood", s["name"].lower()))
    return out


_SHUL_GENERIC = {"congregation", "cong", "bais", "beis", "beit", "beth", "bet", "medrash", "midrash", "medresh", "shul",
                 "shuel", "of", "the", "khal", "khal", "hal", "kehilas", "kehillas", "and", "minyan", "k", "d"}


def _core_tokens(name):
    return frozenset(t for t in re.findall(r"[a-z0-9]+", name.lower().replace("'", "")) if t not in _SHUL_GENERIC)


def merge_shuls(shuls, picker, near_miles=0.3):
    """A shul that is the same place as a neighbourhood in the drop-down shows up once, not twice.

    Same place = the shul names that neighbourhood (explicit "area" in shuls.json) or, once words every shul has
    ("Bais Medrash", "Shul", "of") are removed, its name is the neighbourhood's name and it lies within `near_miles`
    ("Bais Medrash Lutzk" = "Lutzk", "Kol Shimshon" shul = "Kol Shimshon"). A street is never merged: "Spruce Street Shul"
    is a shul on a street, not the street. The neighbourhood entry stays (its pin is where its listings are) and
    gains the shul's name as another spelling and `shul: true`. Returns (shuls still to list, new picker).
    """
    picker = [dict(p) for p in picker]
    by_name = {p["name"].lower(): p for p in picker}
    cores = [(p, _core_tokens(p["name"])) for p in picker if p["name"].split()[-1] not in _STREET_WORDS
             and not _ORDINAL_ONLY.match(p["name"])]
    keep = []
    for s in shuls:
        target = by_name.get((s.get("area") or "").lower())
        if not target:
            core = _core_tokens(s["name"])
            if core:
                for p, pc in cores:
                    if pc == core and haversine_miles(s["lat"], s["lng"], p["lat"], p["lng"]) <= near_miles:
                        target = p
                        break
        if not target:
            keep.append(s)
            continue
        target["shul"] = True
        akas = list(target.get("aka") or [])
        for n in [s["name"]] + list(s.get("aka") or []):
            if n.lower() != target["name"].lower() and n not in akas:
                akas.append(n)
        target["aka"] = akas
    return keep, picker


PREFERRED_STREETS_FILE = pathlib.Path(__file__).parent / "data" / "preferred_streets.json"


def load_preferred_streets(path=PREFERRED_STREETS_FILE):
    """{"forest": "Forest Avenue", ...}: the street people mean by a word that fits several (owner-curated)."""
    try:
        data = json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return {k.lower(): v for k, v in data.get("streets", {}).items()}
