"""Data-quality gate for the weekly rebuild.

check(listings, previous_count) -> (errors, warnings)

* errors   -> the parse almost certainly broke on a new PDF layout. build.py
              aborts without touching listings.json or docs/index.html, so the
              site keeps showing last week's (good) data.
* warnings -> something looks off but the page is still useful. build.py
              publishes anyway and prints them so the weekly report can say
              which location rules to add.

Thresholds were set from real lists: the Aug. 26 and Nov. 18, 2026 lists both
pass; the Nov. list parsed with the old code (25 listings dropped, 40% without
a location) fails.
"""
import re

MIN_LISTINGS = 60          # absolute floor
MAX_DROP = 0.30            # vs. last week's count
MIN_LOCATION_RATE = 0.95
MIN_PHONE_RATE = 0.90
REQUIRED_TYPES = ("Apartment", "House", "Townhouse / Attached")

# Short forms we have rules for (parse.py PLACE_NAMES / ABBREVIATIONS). If one
# survives into a location, a rule is broken or a variant spelling is new.
LEFTOVER = re.compile(
    r"\bWestgt\b|\bEngl\b|\bCentrl\b|\bCnty\b|\bLkwd\b|\bJksn\b|\bPLP\b|\bManch\b|\bClubat\b"
    r"|\bT\.?R\.?\b|\bToms R\.?$"
)
GLUED_WORD = re.compile(r"[a-z]{17,}")   # run-together words, e.g. "Beautifulmodernfurnished"


def _rate(listings, pred):
    return sum(1 for x in listings if pred(x)) / len(listings)


def check(listings, previous_count=None):
    errors, warnings = [], []
    n = len(listings)

    if n < MIN_LISTINGS:
        errors.append(f"only {n} listings parsed (minimum {MIN_LISTINGS})")
        return errors, warnings  # the rate checks below would divide by ~0

    if previous_count:
        drop = (previous_count - n) / previous_count
        if drop > MAX_DROP:
            errors.append(
                f"listing count fell {drop:.0%} ({previous_count} -> {n}); "
                f"limit is {MAX_DROP:.0%} - the PDF layout probably changed")

    loc = _rate(listings, lambda x: x.get("location"))
    if loc < MIN_LOCATION_RATE:
        errors.append(f"only {loc:.0%} of listings have a location (minimum {MIN_LOCATION_RATE:.0%})")

    ph = _rate(listings, lambda x: x.get("phones"))
    if ph < MIN_PHONE_RATE:
        errors.append(f"only {ph:.0%} of listings have a phone number (minimum {MIN_PHONE_RATE:.0%})")

    present = {x.get("type") for x in listings}
    for t in REQUIRED_TYPES:
        if t not in present:
            errors.append(f"no '{t}' listings at all")

    # ---- soft checks ----
    for x in listings:
        where = f"{x.get('id', '?')}"
        loc_text = x.get("location") or ""
        if LEFTOVER.search(loc_text):
            warnings.append(f"unexpanded abbreviation in location {loc_text!r} ({where}) - add a rule in parse.py")
        elif len(loc_text) > 36 or GLUED_WORD.search(loc_text):
            warnings.append(f"location looks malformed: {loc_text!r} ({where})")

    if _rate(listings, lambda x: not x.get("comments")) > 0.15:
        warnings.append("over 15% of listings have no description")
    if _rate(listings, lambda x: GLUED_WORD.search(x.get("comments") or "")) > 0.25:
        warnings.append("over 25% of descriptions contain run-together words")
    if _rate(listings, lambda x: x.get("rent")) < 0.25:
        warnings.append("under 25% of listings have a numeric rent")

    # Map coordinates (only if build.py attached them): never a hard failure -
    # a listing with no coordinates is still shown, it just sorts last by distance.
    if any("geo_unknown" in x for x in listings):
        placed = _rate(listings, lambda x: isinstance(x.get("lat"), (int, float)))
        unknown = sorted({k for x in listings for k in x.get("geo_unknown", [])})
        if unknown:
            shown = ", ".join(unknown[:12]) + (f" (+{len(unknown) - 12} more)" if len(unknown) > 12 else "")
            warnings.append(
                f"{len(unknown)} place name(s) not in places.json, so those listings are not on the map: "
                f"{shown} - add them to places.json after checking each on Google Maps (see CLAUDE.md)")
        unverified = sorted({k for x in listings for k in x.get("geo_unverified", [])})
        if unverified:
            warnings.append(
                f"{len(unverified)} place pin(s) come straight from OpenStreetMap and were never checked on "
                f"Google Maps: {', '.join(unverified[:12])} - verify them (see CLAUDE.md)")
        if placed < 0.70:
            warnings.append(f"only {placed:.0%} of listings can be placed on the map")

    # an address is fine once the owner has confirmed which neighbourhood it belongs to (build.py sets geo_neighborhood)
    addresses = sorted({x.get("location") for x in listings
                        if re.match(r"^\d{1,5}[A-Za-z]?\s+(?:[NSEW]\.?\s+)?[A-Za-z]", str(x.get("location") or ""))
                        and not x.get("geo_neighborhood")})
    if addresses:
        warnings.append(
            f"{len(addresses)} listing location(s) are street addresses, not neighbourhoods: {', '.join(addresses[:8])} - "
            f"map each to the neighbourhood it is in (confirm with the owner); never offer an address as a neighbourhood (see CLAUDE.md)")

    return errors, warnings
