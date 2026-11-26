#!/usr/bin/env python3
"""Parse the Masa U'Matan Lakewood rental list PDF into structured JSON.

Source: https://masaumatan.com/MasaRentals.pdf  (refreshes late Tuesday night)
Output: listings.json  { generated_at, list_date, source_url, count, listings: [...] }
"""
import sys, json, re, io, datetime, urllib.request

import pdfplumber

import abbrev
import segment

SOURCE_URL = "https://masaumatan.com/MasaRentals.pdf"

# Column x-boundaries (points), derived from header + data inspection.
COL = {
    "code":   (78, 99),
    "br":     (99, 112),
    "baths":  (112, 135),
    "loc":    (135, 220),
    "rent":   (219, 252),
    "wepay":  (252, 289),
    "hud":    (289, 321),
    "phone":  (321, 383),
    "comments": (383, 552),
}

CODE_RE = re.compile(r"^[Uu]?\d{0,2}([ATHRathr]{1,3})\d{0,5}_+\d+:?\d*$")
PHONE_RE = re.compile(r"\d{3}[-.\s]?\d{3}[-.\s]?\d{4}")

TYPE_MAP = {"A": "Apartment", "T": "Townhouse / Attached", "H": "House", "R": "Room"}


def fetch_pdf(path_or_url):
    if path_or_url.startswith("http"):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": "Mozilla/5.0"})
        return io.BytesIO(urllib.request.urlopen(req, timeout=60).read())
    return path_or_url


def col_of(x):
    for name, (a, b) in COL.items():
        if a <= x < b:
            return name
    return "comments" if x >= COL["comments"][0] else None


def words_by_row(page, ytol=3.5):
    # Two extraction modes, split at the comments column:
    #  - left of it (code, BR, baths, location, rent, phone) x-sorted words keep
    #    the type letter attached to its code (it is drawn as a separate glyph);
    #  - the comments column uses text-flow order, which keeps words intact on
    #    rows where the PDF interleaves overlapping text layers (otherwise they
    #    shatter into 1-2 letter chunks).
    cx = COL["comments"][0]
    left = [w for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)
            if w["x0"] < cx]
    right = [w for w in page.extract_words(keep_blank_chars=False, use_text_flow=True)
             if w["x0"] >= cx]
    words = left + right
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        placed = False
        for r in rows:
            if abs(r["top"] - w["top"]) <= ytol:
                r["words"].append(w)
                r["top"] = (r["top"] * r["n"] + w["top"]) / (r["n"] + 1)
                r["n"] += 1
                placed = True
                break
        if not placed:
            rows.append({"top": w["top"], "n": 1, "words": [w]})
    for r in rows:
        r["words"].sort(key=lambda w: w["x0"])
    rows.sort(key=lambda r: r["top"])
    return rows


# --- Location naming rules -------------------------------------------------
# The PDF drops spaces ("ClubatJackson21") and abbreviates ("TR", "Westgt.",
# "Lkwd.Comm.Area"). These tables turn those into the names people use.
# Add a line here when a new abbreviation shows up; tests/test_locations.py
# pins the current behaviour.

# Whole place names. Applied first, to the raw text, and tolerant of missing
# or extra spaces. (pattern, canonical name)
PLACE_NAMES = [
    (r"club\s*at\s*jackson\s*21",                         "Club at Jackson 21"),
    (r"mackenzie\s*area\s*(?:toms\s*r(?:iver|\.)?|t\.?\s?r\.?)", "Mackenzie Area Toms River"),
    (r"lkwd\.?\s*comm(?:ons|\.)?\s*area",                   "Lakewood Commons Area"),
    (r"lkwd\.?\s*comm(?:ons|\.)?",                          "Lakewood Commons"),
    (r"west\s*gt\.?|west\s*gate",                           "Westgate"),
    (r"heart\s*of\s*ridge",                                 "Heart of Ridge"),
    (r"bent\s*hook\.?(?:\s*[,/]?\s*(?:t\.?\s?r\.?|toms\s*river))?",   "Bent Hook, Toms River"),
    (r"belz\s*shlav\s*(?:alef|aleph)",                       "Belz Shlav Aleph"),
    # PLP = Pine Lake Park, a community in Manchester Township.
    # Always shown with its township, whether or not the PDF says "Manchester".
    (r"(?:plp|pine\s*lake\s*park)(?:\s*[/,]?\s*manch(?:ester|\.))?", "Pine Lake Park, Manchester"),
]

# Abbreviations inside longer locations. Applied after spacing is repaired.
# (pattern, replacement, flags); each must end at a word edge. "TR" is
# case-sensitive so ordinary lowercase text is never touched.
ABBREVIATIONS = [
    (r"\bT\.?\s?R\.?(?=\s|/|,|$)",   "Toms River", 0),
    (r"\bToms\s+R\.?(?=\s|/|,|$)",    "Toms River", re.I),
    (r"\bJksn\.?(?=\s|/|,|$)",        "Jackson",    re.I),
    (r"\bLkwd\.?(?=\s|/|,|$)",        "Lakewood",   re.I),
    (r"\bEngl\.?(?=\s|/|,|$)",        "England",    re.I),
    (r"\bCentrl\.?(?=\s|/|,|$)",      "Central",    re.I),
    (r"\bCnty\.?(?=\s|/|,|$)",        "County",     re.I),
    (r"\bManch\.?(?=\s|/|,|$)",       "Manchester", re.I),
    (r"\bBrookwd\.?(?=\s|/|,|\d|$)",   "Brookwood",  re.I),
    # owner: a listing "outside Brookwood" belongs to Brookwood
    (r"\bOutside\s+(?=Brookwood\b)",   "",           re.I),
]


def tidy_location(s):
    """Spell out the abbreviations in a location name ("Outside Brookwd 1" -> "Brookwood 1")."""
    for pat, repl, flags in ABBREVIATIONS:
        s = re.sub(pat, repl, s, flags=flags)
    return s


def clean_loc(s):
    s = s.strip()
    trailing_phones = PHONE_RE.findall(s.replace(" ", ""))
    s = re.sub(r"[\d\-.\s]*\d{3}[-.\s]?\d{3}[-.\s]?\d{4}[\d\-.\s]*$", "", s)
    s = re.sub(r"\bCall(\s*or)?\b", "", s, flags=re.I)
    for pat, name in PLACE_NAMES:
        s = re.sub(r"(?<![A-Za-z])(?:" + pat + r")(?![a-z])", name, s, flags=re.I)
    # PDF drops spaces; re-insert before capitals and around slashes.
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", s)
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\b(\d+)\s*(st|nd|rd|th)\b", r"\1\2", s)
    s = re.sub(r",(?=\S)", ", ", s)
    s = re.sub(r"\b([NSEW])(?=[A-Z][a-z]{2,})", r"\1. ", s)   # NApple -> N. Apple (directional initial)
    s = re.sub(r"(?<=[A-Za-z]\.)(?=[A-Z][a-z])", " ", s)   # Rd.Lkwd -> Rd. Lkwd, W.Kennedy -> W. Kennedy
    s = re.sub(r"(?<=[a-z])(near|Near)\b", r" \1", s)
    s = re.sub(r"(?<=[a-z])(area)\b", r" \1", s, flags=re.I)   # Ridgearea -> Ridge area
    s = re.sub(r"\barea\b", "Area", s, flags=re.I)
    # Second pass: names that were glued to the previous word ("nearWestgt.")
    # only become matchable once spacing has been repaired.
    for pat, name in PLACE_NAMES:
        s = re.sub(r"(?<![A-Za-z])(?:" + pat + r")(?![a-z])", name, s, flags=re.I)
    s = tidy_location(s)
    return re.sub(r"\s+", " ", s).strip(" ,/-"), trailing_phones


_GLUE = ("immediately", "available", "furnished", "unfurnished", "kitchen", "house",
         "home", "apartment", "renovated", "bedroom", "bedrooms", "basement", "bathroom",
         "washer", "dryer", "working", "location", "included", "utilities", "backyard",
         "parking", "porch", "storage", "shuls", "yeshiva", "near", "large", "spacious",
         "beautiful", "private", "separate", "entrance", "central", "heating", "cooling")

def _fix_spaced_runs(s):
    """Rejoin runs of 4+ single letters ("E x c e l l e n t" -> "Excellent")
    that the PDF's kerning splits, without touching normal words."""
    toks = s.split(" ")
    out, i = [], 0
    while i < len(toks):
        j = i
        while j < len(toks) and len(toks[j].strip(".,;:")) == 1 and toks[j].strip(".,;:").isalpha():
            j += 1
        if j - i >= 4:
            out.append("".join(toks[i:j]))
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def clean_comment(s):
    s = re.sub(r"\(cid:\d+\)", "", s)
    s = _fix_spaced_runs(s)
    toks = s.split()
    if toks and sum(1 for t in toks if len(t) == 1) / len(toks) > 0.28:
        return ""  # too fragmented to be trustworthy
    s = re.sub(r"(?<=[a-z.,])(?=[A-Z])", " ", s)
    s = segment.rejoin_split_words(s)                         # "P artly" -> "Partly" (a stray space after the first letter)
    s = segment.join_hyphenated(s)                            # "learn- ing" -> "learning" (a line break in the PDF)
    s = segment.fix_glued(s)                                  # "locationneareverything" -> "location near everything"
    s = re.sub(r"(?<=[A-Za-z]{2}[.,;:])(?=[A-Za-z0-9])", " ", s)   # "Av.imm." -> "Av. imm."
    s = abbrev.expand(s)                                      # "Av. imm." -> "Available immediately" (Masa U'Matan charges by the word)
    for w in _GLUE:
        s = re.sub(r"(?<=[a-z])(" + w + r")\b", r" \1", s, flags=re.I)
    s = re.sub(r"\bun furnished\b", "unfurnished", s, flags=re.I)
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([.,;:])", r"\1", s)
    # Cut where a neighbouring display ad has bled into the text.
    s = re.split(r"\s*(?:\S*@\S+|https?://|www\.\S+|washingtonsquare|"
                 r"CALL OR TEXT|Visit us|Luxury Living)", s, maxsplit=1, flags=re.I)[0].strip()
    # Drop a trailing run of very short fragments (kerning garble tail).
    s = re.sub(r"(?:\b\w{1,2}\b[ ,]*){5,}$", "", s).strip(" ,;:-")
    if len(s) > 420:                                          # spelled-out text is longer than the PDF's shorthand
        s = s[:417].rsplit(" ", 1)[0] + "…"
    return s


def derive_type(code):
    m = CODE_RE.match(code)
    letters = (m.group(1).upper() if m else "")
    for ch in "RHTA":  # priority
        if ch in letters:
            return TYPE_MAP[ch]
    return "Other"



# --- Reading the page by its table cells ------------------------------------------------
# Every listing is one row of ruled cells (Type | BR | Baths | Location | $ | We pay | HUD |
# Telephone | Comments). The cell rectangles are drawn in the PDF, so they say exactly which
# words belong to which listing. That is far more reliable than guessing from text: codes
# come with letters missing, the type letters sometimes sit on another line, bedroom digits
# get glued onto the code, phone numbers shatter into single characters, and ad banners carry
# phantom codes. The old text-anchor method (_parse_page_by_text) remains as a fallback if the
# PDF layout ever stops having cell rectangles.

CELL_LOC = (133, 220)          # the Location cell's x extent; one per listing row
CELL_X = {"br": (97, 112), "baths": (112, 133), "loc": (133, 220), "rent": (220, 248),
          "wepay": (248, 291), "hud": (291, 321), "phone": (321, 385)}
COMMENTS_X = 385

# A listing code: optional junk/"U" prefix, type letters (sometimes missing), number, _day:index.
# The bedroom digit is sometimes glued on after the index ("..._1049:103" is index 10, 3 bedrooms).
CODE_LOOSE = re.compile(r"^(?P<pre>[A-Za-z]{0,2}?[Uu]?\d{0,2})(?P<type>[ATHRathr]{0,3})(?P<num>\d{0,5})"
                        r"_+(?P<a>\d+):?(?P<b>\d*)(?P<tail>.*)$")
TYPE_ONLY = re.compile(r"^[Uu]?([ATHR]{1,3})$")
# 10-digit numbers, or the 7-digit local numbers some listings print without an area code.
PHONE_ANY = re.compile(r"(?<!\d)(?:(\d{3})[-.]?)?(\d{3})[-.]?(\d{4})(?!\d)")
LOCAL_AREA_CODE = "732"        # 7-digit numbers in this list are Ocean/Monmouth County local numbers


def find_phones(text):
    """Phone numbers in `text` (spaces already removed), as 'aaa-bbb-cccc'. A 7-digit number gets 732."""
    out = []
    for m in PHONE_ANY.finditer(text):
        num = f"{m.group(1) or LOCAL_AREA_CODE}-{m.group(2)}-{m.group(3)}"
        if num not in out:
            out.append(num)
    return out


def row_cells(page, tol=2):
    """[(top, bottom)] of every listing row on the page, in order, or [] if the page has no cells.

    Built from the left-hand cells (Type, BR, Baths, Location): an ad banner can replace the
    Location cell of a row, but its Type/BR/Baths cells are still drawn."""
    left_edges = (83, 97, 112, 133)
    spans = sorted({(round(r["top"], 1), round(r["bottom"], 1)) for r in page.rects
                    if r["height"] > 8 and r["height"] < 60 and r["x1"] < 225
                    and any(abs(r["x0"] - e) <= tol for e in left_edges)})
    merged = []
    for t, b in spans:
        if merged and abs(merged[-1][0] - t) < 1.0:          # the same row seen through another cell
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((t, b))
    return merged


def _flow_lines(words, ytol=3.5):
    """Group words into visual lines (top within ytol), left to right inside each line."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for ln in lines:
            if abs(ln["top"] - w["top"]) <= ytol:
                ln["words"].append(w)
                break
        else:
            lines.append({"top": w["top"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
    lines.sort(key=lambda ln: ln["top"])
    return lines


def _digits(s):
    return sum(c.isdigit() for c in s)


def parse_row(words, page_no=0, row_no=0):
    """One listing from the words lying inside its row. `words` are pdfplumber word dicts
    (text, x0, x1, top, bottom). Returns a listing dict, or None if it is not a listing."""
    if any(w["text"] in ("Telephone", "Location") for w in words):
        return None                                           # header row
    code, type_letters, br_extra, bed_tail = "", "", "", ""
    cols = {k: [] for k in ("br", "baths", "loc", "rent", "wepay", "hud", "phone", "comments")}
    phone_chunks, extra_comments = [], []
    for w in words:
        t = w["text"]
        cx = (w["x0"] + w["x1"]) / 2
        m = CODE_LOOSE.match(t) if w["x0"] < 200 else None
        if m and not code:
            b = m.group("b")
            code = t[:m.start("b")] + b[:2]
            br_extra = b[2:]
            bed_tail = m.group("tail")
            type_letters = m.group("type").upper()
            continue
        mt = TYPE_ONLY.match(t) if w["x0"] < 125 else None
        if mt:
            type_letters = type_letters or mt.group(1)
            continue
        if w["x0"] >= COMMENTS_X - 2:
            cols["comments"].append(w)
            continue
        # a whole phone number (or a long digit run) in the rent / location area, e.g. "FREE732-814-4648"
        if w["x0"] >= 215 and _digits(t) >= 7:
            phone_chunks.append(w)
            continue
        placed = False
        for name, (a, b2) in CELL_X.items():
            if a <= cx < b2:
                cols[name].append(w)
                placed = True
                break
        if not placed and cx >= COMMENTS_X:
            cols["comments"].append(w)
    # phones: the telephone cell, line by line so shattered digits rejoin, plus whole numbers found elsewhere
    phones = []
    for w in phone_chunks:                      # one word holding a whole number, maybe glued to the next word
        found = find_phones(w["text"])
        if not found:
            m = re.match(r"(\d{3})[-.]?(\d{3})[-.]?(\d{4})", w["text"])    # "646-379-04871-family"
            found = [f"{m.group(1)}-{m.group(2)}-{m.group(3)}"] if m else []
        phones += [p for p in found if p not in phones]
    for ln in _flow_lines(cols["phone"]):
        phones += [p for p in find_phones("".join(w["text"] for w in ln["words"])) if p not in phones]
    # ad banners replace the HUD/phone cells with text; keep that text as the comment
    for w in cols["hud"] + cols["phone"]:
        if sum(c.isalpha() for c in w["text"]) >= 3 and _digits(w["text"]) == 0 and "(cid" not in w["text"]:
            extra_comments.append(w)
    # location: lines of the Location cell
    loc_words = [w for w in cols["loc"] if "(cid" not in w["text"] and not re.fullmatch(r"[\d,]{3,5}|\d[½¼¾]?", w["text"])]
    loc_lines = []
    trailing = []
    for ln in _flow_lines(loc_words):
        part, ph = clean_loc(" ".join(w["text"] for w in ln["words"]))
        trailing += ph
        if part:
            loc_lines.append(part)
    loc = " / ".join(loc_lines)
    for p in trailing:
        d = re.sub(r"\D", "", p)
        norm = f"{d[:3]}-{d[3:6]}-{d[6:10]}" if len(d) >= 10 else None
        if norm and norm not in phones:
            phones.append(norm)
    # rent
    rent_txt = "".join(w["text"] for w in sorted(cols["rent"], key=lambda w: (round(w["top"]), w["x0"])))
    call_to_discuss = any("(cid" in w["text"] for w in cols["rent"])
    accepts_hud = any("(cid" in w["text"] for w in cols["hud"])
    rent_num = None
    mnum = re.search(r"\d[\d,]{2,5}", rent_txt)
    if mnum:
        rent_num = int(mnum.group().replace(",", ""))
    weekly = bool(re.search(r"week", rent_txt, re.I))
    free = any(re.match(r"FREE", w["text"]) for w in phone_chunks) or bool(re.search(r"FREE", rent_txt))
    negotiable = bool(re.search(r"NEG", rent_txt, re.I))
    wepay = "".join(c for c in "".join(w["text"] for w in cols["wepay"]) if c in "GEWH")
    comments = clean_comment(" ".join(w["text"] for ln in _flow_lines(extra_comments + cols["comments"])
                                      for w in ln["words"]))
    # bedrooms / baths: the small number tokens at the left, in reading order (banner rows shift them
    # sideways, so fixed x positions are not reliable). "5" then "2½" = 5 bd, 2½ ba; a lone number is
    # the bedrooms unless it sits in the baths column, or the bedroom digit was glued onto the code.
    nums = sorted((w for w in words if w["x0"] < 135 and re.fullmatch(r"\d{1,2}\+?[½¼¾]?|\d?[½¼¾]", w["text"])),
                  key=lambda w: w["x0"])
    br, baths = "", ""
    if br_extra:
        br = re.match(r"\d*", br_extra).group()
        if nums:
            baths = nums[0]["text"]
    elif len(nums) >= 2:
        br, baths = nums[0]["text"], nums[1]["text"]
    elif nums:
        if (nums[0]["x0"] + nums[0]["x1"]) / 2 < CELL_X["baths"][0]:
            br = nums[0]["text"]
        else:
            baths = nums[0]["text"]
    br = (re.match(r"\d+", br).group() if re.match(r"\d+", br) else "")
    mb = re.match(r"(\d+)\s*([½¼¾])?", baths) or re.match(r"()([½¼¾])", baths)
    baths = (mb.group(1) + (mb.group(2) or "")) if mb else ""
    # phone found nowhere in its cell: a number written in the comments is still its number
    if not phones:
        phones = find_phones(re.sub(r"\s+", "", " ".join(w["text"] for w in cols["comments"])))
    if not (type_letters or br or baths):
        return None                                           # an ad banner, not a listing
    if free and not rent_num:
        return None                                           # "FREE": a charity ad (owner: not a rental)
    if not loc and not comments and not phones:
        return None
    umap = {"G": "Gas", "E": "Electric", "W": "Water", "H": "Heat"}
    rent_display = (f"${rent_num:,}/week" if weekly and rent_num else
                    f"${rent_num:,}/mo" if rent_num else
                    "Call to discuss" if call_to_discuss else "Contact for rent")
    return {
        "id": code or f"p{page_no}r{row_no}",
        "type": derive_type_letters(type_letters),
        "utilities_included": [umap[c] for c in "GEWH" if c in wepay],
        "bedrooms": br,
        "bedrooms_num": int(br) if br.isdigit() else None,
        "baths": baths,
        "location": loc,
        "rent": None if weekly else rent_num,
        "rent_period": "week" if weekly and rent_num else "month",
        "negotiable": negotiable,
        "rent_display": rent_display,
        "landlord_pays": wepay,
        "accepts_hud": accepts_hud,
        "phones": phones[:3],
        "furnished": bool(re.search(r"\bfurnished\b", comments, re.I)),
        "comments": comments,
    }


def page_words(page):
    """All words on the page: x-sorted left of the comments column, text-flow order inside it."""
    cx = COL["comments"][0]
    left = [w for w in page.extract_words(keep_blank_chars=False, use_text_flow=False) if w["x0"] < cx]
    right = [w for w in page.extract_words(keep_blank_chars=False, use_text_flow=True) if w["x0"] >= cx]
    return left + right


SKIPPED = []     # (page, text) of rows left out because they are ad banners, not listings


def _parse_page_by_cells(page, cells, page_no):
    tops = [c[0] for c in cells]
    import bisect
    rows = [[] for _ in cells]
    for w in page_words(page):
        cy = (w["top"] + w["bottom"]) / 2
        i = bisect.bisect_right(tops, cy + 0.01) - 1
        if i >= 0 and cy <= cells[i][1] + 2:
            rows[i].append(w)
    out = []
    for i, words in enumerate(rows):
        x = parse_row(words, page_no, i)
        if x:
            out.append(x)
        elif words and not any(w["text"] in ("Telephone", "Location") for w in words):
            SKIPPED.append((page_no, " ".join(w["text"] for w in sorted(words, key=lambda w: (w["top"], w["x0"])))[:90]))
    return out


def derive_type_letters(letters):
    for ch in "RHTA":  # priority
        if ch in (letters or "").upper():
            return TYPE_MAP[ch]
    return "Other"


def _parse_page_by_text(page):
    listings = []
    rows = words_by_row(page)
    # locate listing anchors
    anchors = []
    for i, r in enumerate(rows):
        first = r["words"][0]
        if first["x0"] < COL["code"][1] and CODE_RE.match(first["text"]):
            has_phone = any(PHONE_RE.search(w["text"]) for w in r["words"])
            if has_phone or any(COL["phone"][0] <= w["x0"] < COL["phone"][1] for w in r["words"]):
                anchors.append(i)
    # Location text is vertically centred on the listing's first line and
    # may wrap onto a line ABOVE or BELOW it, so row-block membership is
    # unreliable. Assign every location-column word to the vertically
    # nearest listing instead.
    a_tops = [rows[ri]["top"] for ri in anchors]
    loc_words = {k: [] for k in range(len(anchors))}
    lx0, lx1 = COL["loc"]
    for r in rows:
        if any(w["text"] == "Telephone" for w in r["words"]) or not a_tops:
            continue
        dists = [abs(r["top"] - t) for t in a_tops]
        k = min(range(len(dists)), key=dists.__getitem__)
        if dists[k] > 14:
            continue
        for w in r["words"]:
            if lx0 - 6 <= w["x0"] < lx1 and "(cid" not in w["text"] \
                    and not re.fullmatch(r"[\d,]{3,5}|\d[½¼¾]?", w["text"]):
                loc_words[k].append((round(r["top"]), w["x0"], w["text"]))
    for a_idx, ri in enumerate(anchors):
        end = anchors[a_idx + 1] if a_idx + 1 < len(anchors) else len(rows)
        block = rows[ri:end]
        # A listing is at most ~5 wrapped comment lines tall. Anything
        # further down belongs to a listing whose anchor row was mangled
        # (common around the mid-page ad boxes on page 1).
        atop = block[0]["top"]
        block = [r for r in block if r["top"] - atop < 46]
        buckets = {k: [] for k in COL}
        for br_i, r in enumerate(block):
            for w in r["words"]:
                c = col_of(w["x0"])
                if c is None:
                    continue
                if br_i > 0 and c != "comments":
                    # continuation lines: comments are trusted. Location,
                    # rent and utilities are vertically centred in the cell,
                    # so on 2-line listings they land on the 2nd row: accept
                    # them there (row 1 only). A stacked 2nd phone is also
                    # allowed on the row right below.
                    if br_i == 1 and c in ("loc", "rent", "wepay"):
                        buckets[c].append(w["text"])
                    elif c == "phone" and br_i == 1 and PHONE_RE.search(w["text"]):
                        buckets["phone"].append(w["text"])
                    continue
                buckets[c].append(w["text"])
        code = buckets["code"][0] if buckets["code"] else ""
        lw = sorted(loc_words[a_idx])
        lines = []
        for top, _x, text in lw:
            if lines and lines[-1][0] == top:
                lines[-1][1].append(text)
            else:
                lines.append((top, [text]))
        # Full-width free-text ads spill description words into this
        # column; real locations are short phrases of short tokens.
        lines = [(tp, t) for tp, t in lines
                 if len(" ".join(t)) <= 36 and max(len(x) for x in t) <= 20
                 and not (len(t) >= 4 and max(len(x) for x in t) <= 2)]
        loc_parts = [clean_loc(" ".join(t))[0] for _, t in lines]
        loc_ph = [p for _, t in lines for p in clean_loc(" ".join(t))[1]]
        loc = " / ".join(p for p in loc_parts if p)
        loc_phones = loc_ph
        phone_join = " ".join(buckets["phone"])
        phones = PHONE_RE.findall(phone_join.replace(" ", "")) or PHONE_RE.findall(phone_join)
        for lp in loc_phones:
            if lp not in phones:
                phones.append(lp)
        phones = list(dict.fromkeys(phones))[:3]
        rent_raw = " ".join(buckets["rent"]).strip()
        rent_num = None
        mnum = re.search(r"\d{3,5}", rent_raw.replace(",", ""))
        if mnum:
            rent_num = int(mnum.group())
        call_to_discuss = "(cid:2)" in rent_raw or "(cid:2)" in " ".join(buckets["hud"])
        wepay = "".join(c for c in "".join(buckets["wepay"]) if c in "GEWH")
        hud_raw = "".join(buckets["hud"]).replace("(cid:2)", "").strip()
        # The HUD column only ever carries a short yes-marker; anything
        # longer is mis-bucketed comment text.
        accepts_hud = bool(hud_raw) and len(hud_raw) <= 4 and not hud_raw.isdigit()
        comments = clean_comment(" ".join(buckets["comments"]))
        br = next((t for t in buckets["br"] if re.search(r"\d", t)), "")
        br = (re.match(r"\d+", br).group() if re.match(r"\d+", br) else "")
        baths = ""
        for t in buckets["baths"]:
            mb = re.match(r"(\d+)\s*([½¼¾])?", t)
            if mb:
                baths = mb.group(1) + (mb.group(2) or "")
                break
        if not loc and not comments and not phones:
            continue
        umap = {"G": "Gas", "E": "Electric", "W": "Water", "H": "Heat"}
        utilities = [umap[c] for c in "GEWH" if c in wepay]
        listings.append({
            "id": code,
            "type": derive_type(code),
            "utilities_included": utilities,
            "bedrooms": br,
            "bedrooms_num": int(re.search(r"\d+", br).group()) if re.search(r"\d+", br) else None,
            "baths": baths,
            "location": loc,
            "rent": rent_num,
            "rent_display": (f"${rent_num:,}/mo" if rent_num else ("Call to discuss" if call_to_discuss else (rent_raw or "Contact for rent"))),
            "landlord_pays": wepay,
            "accepts_hud": accepts_hud,
            "phones": phones,
            "furnished": bool(re.search(r"\bfurnished\b", comments, re.I)),
            "comments": comments,
        })
    return listings


def parse(fileobj):
    listings = []
    list_date = None
    del SKIPPED[:]
    with pdfplumber.open(fileobj) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            if list_date is None:
                m = re.search(r"Rental List of\s+(.+?20\d\d)", txt)
                if m:
                    list_date = re.sub(r"\s+", " ", m.group(1)).strip()
            cells = row_cells(page)
            if cells:
                listings.extend(_parse_page_by_cells(page, cells, page_no))
            else:                                    # no ruled cells: fall back to guessing from the text
                listings.extend(_parse_page_by_text(page))
    return list_date, listings


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCE_URL
    out = sys.argv[2] if len(sys.argv) > 2 else "listings.json"
    list_date, listings = parse(fetch_pdf(src))
    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "list_date": list_date,
        "source_url": SOURCE_URL,
        "source_site": "https://masaumatan.com",
        "count": len(listings),
        "listings": listings,
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"parsed {len(listings)} listings, list_date={list_date!r} -> {out}")


if __name__ == "__main__":
    main()
