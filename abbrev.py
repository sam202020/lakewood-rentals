"""Spell out the abbreviations in listing descriptions.

Masa U'Matan charges by the word, so the descriptions are written in shorthand ("Av. imm.", "furn. apt.", "lg. bkyd.",
"WD", "SS appliances", "10 min. walk"). On the site there is room to spell them out. Rules are matched on whole words
only and look at the neighbouring words where an abbreviation has two meanings:

    Sep. 1 -> September 1          Sep. kitchen -> Separate kitchen
    10 min. walk -> 10-minute walk 3 mo. min. -> 3 months minimum
    Inc. wifi -> Includes wifi     utilities incl. -> utilities included

The text is rewritten in ONE left-to-right pass, so every decision can look at what has already been written:
  * the abbreviation's own full stop is dropped mid-sentence ("furn. apt. near" -> "furnished apartment near") and kept
    where a sentence ends ("Beautiful apt. Great location." -> "Beautiful apartment. Great location.");
  * a capital letter is kept if the abbreviation had one ("Av." -> "Available"), and an ALL-CAPS one (WD, LR) is
    capitalised only at the start of a sentence; a lower-case abbreviation stays lower-case.
Add a rule to RULES for a new abbreviation, with a test in tests/test_abbrev.py.
"""
import re

MONTHS = {"jan": "January", "feb": "February", "mar": "March", "apr": "April", "jun": "June", "jul": "July",
          "aug": "August", "sep": "September", "sept": "September", "oct": "October", "nov": "November",
          "dec": "December"}
DIRECTIONS = {"E": "East", "W": "West", "N": "North", "S": "South"}
STREETS = {"ave": "Avenue", "rd": "Road", "blvd": "Boulevard", "ln": "Lane", "ct": "Court"}

# not preceded / followed by a letter (so "furn" inside "unfurnished" or "imm" inside "immediately" never matches)
B = r"(?<![A-Za-z])"
E = r"(?![A-Za-z])"
DOT = r"\.?"


class Ctx:
    """What the replacement functions can see: the original text, and the output written so far."""

    def __init__(self, text, prefix):
        self.text, self.prefix = text, prefix

    def sentence_start(self):
        return self.prefix.strip() == "" or re.search(r"[.!?]\s+$", self.prefix) is not None


def _case(expansion, ab, ctx):
    letters = re.sub(r"[^A-Za-z]", "", ab)
    if not letters or letters[0].islower():
        return expansion                                   # "imm." stays lower-case
    shouted = re.sub(r"s$", "", letters)                   # "BRs" counts as shouted too
    if len(shouted) > 1 and shouted.isupper():             # WD, LR, EIK, BRs: a capital only at the start of a sentence
        return expansion[0].upper() + expansion[1:] if ctx.sentence_start() else expansion
    return expansion[0].upper() + expansion[1:]            # "Av." -> "Available"


# capitalised words that continue a sentence ("furn. Choson/Kallah apt."): no sentence ends before them
CONTINUES = {"choson", "chosson", "kallah", "kalla", "shul", "shuls", "yeshiva", "heimishe", "sephardic", "ashkenaz",
             "pesach", "shabbos", "kosher"}


def _stop(m, ctx, never_ends=False, soft=False, digit_ends=True):
    """The abbreviation's own full stop: kept where a sentence ends, dropped mid-sentence.
    never_ends: it never ends a sentence ("Av.", "lg."). soft: it can, unless a continuing noun follows."""
    if not m.group(0).endswith("."):
        return ""
    rest = ctx.text[m.end():]
    if rest.strip() == "":
        return "" if never_ends else "."
    if never_ends:
        return ""
    nxt = re.match(r"\s+([A-Z][A-Za-z]*|\d)", rest)      # a capital or (usually) a digit starts the next sentence
    if not nxt or (nxt.group(1).isdigit() and not digit_ends):
        return ""
    return "" if (soft and nxt.group(1).lower() in CONTINUES) else "."


def _make(expansion, plural=None, never_ends=False, soft=False):
    def repl(m, ctx):
        ab = m.group(0)
        word = ab.rstrip(".")
        out = plural if (plural and word.lower().endswith("s")) else expansion
        return _case(out, ab, ctx) + _stop(m, ctx, never_ends, soft)
    return repl


def _month(m, ctx):
    return MONTHS[m.group(1).lower()] + _stop(m, ctx, digit_ends=False)        # "Dec. 1" is a date, not a sentence end


def _sep(m, ctx):                              # Sep. 1 -> September 1 ; Sep. kitchen -> Separate kitchen
    rest = ctx.text[m.end():]
    if re.match(r"\s*\d", rest) or rest.strip() == "" or re.match(r"\s*[.,;]", rest):
        return "September" + _stop(m, ctx, digit_ends=False)
    return _case("separate", m.group(0), ctx) + _stop(m, ctx, never_ends=True)


def _inc(m, ctx):                              # "Inc. wifi" (starts a sentence) -> Includes; "utilities incl." -> included
    word = "Includes" if ctx.sentence_start() else "included"
    return word + _stop(m, ctx)


def _poss(m, ctx):                             # "Poss. furnished" -> Possibly furnished ; "office/poss." -> office/possible
    word = "possibly" if re.match(r"\s+[a-z]", ctx.text[m.end():]) else "possible"
    return _case(word, m.group(0), ctx) + _stop(m, ctx)


def _opt(m, ctx):                              # "Opt. furnished" -> Optionally furnished
    return _case("optionally", m.group(0), ctx) + _stop(m, ctx, never_ends=True)


def _num_unit(one, many):
    def repl(m, ctx):
        n = m.group(1)
        return f"{n} {one if n == '1' else many}" + _stop(m, ctx)
    return repl


def _bedrooms(m, ctx):
    n = m.group(1)
    return f"{n} " + ("bedroom" if n == "1" else "bedrooms") + _stop(m, ctx)


def _sqft_number(m, ctx):                      # 3000 s.f, / 2500 Sf. -> square feet
    return " square feet" + _stop(m, ctx)


def _direction(m, ctx):
    return DIRECTIONS[m.group(1)] + " "


def _street(m, ctx):
    return " " + STREETS[m.group(1).lower()] + _stop(m, ctx)


# (pattern, replacement function). When two rules match at the same place the earlier one wins.
RULES = [
    # months and "Sep."
    (re.compile(B + r"(?:Sep|Sept)" + DOT + E, re.I), _sep),
    (re.compile(B + r"(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Oct|Nov|Dec)" + r"\." + E), _month),
    # sizes and times (they need the number in front)
    (re.compile(r"(?<![A-Za-z])(\d+)\s*-?\s*ft\.?(?=\s+ceilings?)", re.I), lambda m, c: f"{m.group(1)}-foot"),
    (re.compile(B + r"sq\.?\s*(?:ft|feet)" + DOT + E, re.I), _make("square feet")),
    (re.compile(r"(?<=\d)\s*(?:s\.f|sf)" + DOT + E, re.I), _sqft_number),
    (re.compile(r"(?<![A-Za-z])(\d+)\s*min" + DOT + r"(?=\s+(?:walk|drive|ride|away|from|to|by)\b)", re.I),
     lambda m, c: f"{m.group(1)}-minute"),
    (re.compile(r"(?<![A-Za-z])(\d+)\s*mos?" + DOT + E, re.I), _num_unit("month", "months")),
    (re.compile(B + r"ft" + DOT + E, re.I), _make("feet")),
    (re.compile(B + r"min" + DOT + E, re.I), _make("minimum")),
    # availability (these never end a sentence)
    (re.compile(B + r"Av(?:ail)?\." + r"(?=\s)", re.I), _make("available", never_ends=True)),
    (re.compile(B + r"imm" + DOT + E, re.I), _make("immediately")),
    # state of the unit
    (re.compile(B + r"unfurn" + DOT + E, re.I), _make("unfurnished", soft=True)),
    (re.compile(B + r"furn" + DOT + E, re.I), _make("furnished", soft=True)),
    (re.compile(B + r"unfin" + DOT + E, re.I), _make("unfinished", soft=True)),
    (re.compile(B + r"fin\." + E, re.I), _make("finished", soft=True)),
    (re.compile(B + r"cond" + r"\." + E, re.I), _make("condition")),
    (re.compile(B + r"Upgr" + DOT + E, re.I), _make("upgraded", never_ends=True)),
    (re.compile(B + r"beaut" + r"\." + E, re.I), _make("beautiful", never_ends=True)),
    (re.compile(B + r"Perf" + r"\." + E, re.I), _make("perfect", never_ends=True)),
    (re.compile(B + r"Opt" + r"\." + E, re.I), _opt),
    (re.compile(B + r"Poss" + r"\." + E, re.I), _poss),
    (re.compile(B + r"(?:Inc|Incl)" + r"\." + E, re.I), _inc),
    (re.compile(B + r"approx" + DOT + E, re.I), _make("approximately", never_ends=True)),
    (re.compile(B + r"appli" + r"\." + E, re.I), _make("appliances")),
    # shouted initials
    (re.compile(r"(?<![A-Za-z/])LR\s*/\s*DR" + DOT + E, re.I), _make("living room/dining room")),
    (re.compile(r"(?<![A-Za-z/])LR" + DOT + E), _make("living room")),
    (re.compile(r"(?<![A-Za-z/])DR" + DOT + E), _make("dining room")),
    (re.compile(r"(?<![A-Za-z/])EIK" + DOT + E), _make("eat-in kitchen")),
    (re.compile(r"(?<![A-Za-z/])(\d+)\s*(?:br|bd|bdr)s?" + DOT + E, re.I), _bedrooms),
    (re.compile(r"(?<![A-Za-z/])BRs?" + DOT + E), _make("bedroom", "bedrooms")),
    (re.compile(r"(?<![A-Za-z/])AC" + DOT + E), _make("air conditioning")),
    (re.compile(r"(?<![A-Za-z/])(?:WD|W/D)" + DOT + E), _make("washer/dryer")),
    (re.compile(r"(?<![A-Za-z/])SS(?=\s+(?:appliances?|kitchen|fridge))"), _make("stainless steel")),
    # places in the unit
    (re.compile(B + r"apts?" + DOT + E, re.I), _make("apartment", "apartments")),
    (re.compile(B + r"(?:bsmt|basemt|bsmnt|bsment)" + DOT + E, re.I), _make("basement")),
    (re.compile(B + r"(?:bkyd|bkyard|backyd)" + DOT + E, re.I), _make("backyard")),
    (re.compile(B + r"(?:bedrms?|bdrms?)" + DOT + E, re.I), _make("bedrooms")),
    (re.compile(B + r"rms?" + r"\." + E, re.I), _make("room", "rooms")),
    (re.compile(B + r"fam" + r"\." + E, re.I), _make("family", never_ends=True)),
    (re.compile(B + r"Lg" + r"\." + E, re.I), _make("large", never_ends=True)),
    (re.compile(B + r"Lg(?=\s+[a-z])", re.I), _make("large")),                       # "Lg lot"
    (re.compile(B + r"Sm" + r"\." + E), _make("small", never_ends=True)),
    (re.compile(B + r"priv" + DOT + E, re.I), _make("private", never_ends=True)),
    (re.compile(B + r"w/\s*(?=[A-Za-z])(?!d(?![A-Za-z]))", re.I), lambda m, c: "with "),
    (re.compile(B + r"dist" + r"\." + E, re.I), _make("distance", never_ends=True)),
    (re.compile(B + r"grnd" + DOT + E, re.I), _make("ground", never_ends=True)),
    (re.compile(B + r"thru-out" + DOT + E, re.I), _make("throughout")),
    (re.compile(B + r"thru" + E, re.I), _make("through", never_ends=True)),
    (re.compile(B + r"Br\.(?=\s+new\b)", re.I), _make("brand", never_ends=True)),             # "Br. new" = Brand new
    (re.compile(B + r"St\.\s+(?=steel\b)", re.I), lambda m, c: _case("stainless ", m.group(0), c)),   # "St. steel kitchen"
    # names
    (re.compile(B + r"Rt" + r"\." + r"\s*(?=\d)"), lambda m, c: "Route "),
    (re.compile(B + r"([ENSW])\.\s+(?=[A-Z][a-z])"), _direction),
    (re.compile(r"(?<=[A-Za-z0-9]{3})\s+(Ave|Rd|Blvd|Ln|Ct)\." + r"(?![A-Za-z])"), _street),
]


def expand(text):
    """Spell out the abbreviations in a description; everything else is left as it was."""
    text = text.replace("...", "\u2026")                    # an ellipsis is not an abbreviation's full stop
    # 1. find every match, then keep the earliest non-overlapping ones (an earlier rule wins a tie)
    found = []
    for order, (pattern, repl) in enumerate(RULES):
        for m in pattern.finditer(text):
            found.append((m.start(), order, m, repl))
    found.sort(key=lambda f: (f[0], f[1]))
    chosen, last_end = [], 0
    for start, _order, m, repl in found:
        if start >= last_end:
            chosen.append((m, repl))
            last_end = m.end()
    # 2. rewrite left to right, so each replacement can see what came before it
    out, pos = [], 0
    for m, repl in chosen:
        out.append(text[pos:m.start()])
        out.append(repl(m, Ctx(text, "".join(out))))
        pos = m.end()
    out.append(text[pos:])
    result = "".join(out)
    result = re.sub(r"\s+([.,;:!?])", r"\1", result)
    result = re.sub(r"(?<=[A-Za-z])/\s+(?=[A-Za-z])", "/", result)               # "Choson/ Kallah" -> "Choson/Kallah"
    result = re.sub(r"\b(Available)\b\.?\s+(?=Available\b)", "", result)         # "Av. Av. imm." printed twice
    result = re.sub(r"(?<![.])\.\.(?![.])", ".", result)                         # "etc.." -> "etc."
    return re.sub(r"\s{2,}", " ", result).strip().replace("\u2026", "...")
