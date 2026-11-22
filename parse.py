#!/usr/bin/env python3
"""Parse the Masa U'Matan Lakewood rental list PDF into structured JSON.

Source: https://masaumatan.com/MasaRentals.pdf  (refreshes late Tuesday night)
Output: listings.json  { generated_at, list_date, source_url, count, listings: [...] }
"""
import sys, json, re, io, datetime, urllib.request

import pdfplumber

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


def clean_loc(s):
    s = s.strip()
    trailing_phones = PHONE_RE.findall(s.replace(" ", ""))
    s = re.sub(r"[\d\-.\s]*\d{3}[-.\s]?\d{3}[-.\s]?\d{4}[\d\-.\s]*$", "", s)
    s = re.sub(r"\bCall(\s*or)?\b", "", s, flags=re.I)
    # PDF drops spaces; re-insert before capitals and around slashes.
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", s)
    s = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", s)
    s = re.sub(r"\s*&\s*", " & ", s)
    s = re.sub(r"\b(\d+)\s*(st|nd|rd|th)\b", r"\1\2", s)
    s = re.sub(r",(?=\S)", ", ", s)
    s = re.sub(r"(?<=[a-z])(near|Near)\b", r" \1", s)
    s = re.sub(r"(?<=[a-z])(area|Area)$", r" area", s)
    s = re.sub(r"\barea\b", "area", s)
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
    if len(s) > 300:
        s = s[:297].rsplit(" ", 1)[0] + "…"
    return s


def derive_type(code):
    m = CODE_RE.match(code)
    letters = (m.group(1).upper() if m else "")
    for ch in "RHTA":  # priority
        if ch in letters:
            return TYPE_MAP[ch]
    return "Other"


def parse(fileobj):
    listings = []
    list_date = None
    with pdfplumber.open(fileobj) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if list_date is None:
                m = re.search(r"Rental List of\s+(.+?20\d\d)", txt)
                if m:
                    list_date = re.sub(r"\s+", " ", m.group(1)).strip()

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
                         if len(" ".join(t)) <= 36 and max(len(x) for x in t) <= 20]
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
