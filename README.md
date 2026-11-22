# Lakewood NJ Area Rentals

A searchable web index of Lakewood / Jackson area rentals, rebuilt every week from
the **Masa U'Matan** rental list PDF (<https://masaumatan.com/MasaRentals.pdf>).

This is an unofficial search tool. It is not affiliated with Masa U'Matan, and every
view links back to `masaumatan.com` and the original PDF. The PDF is authoritative.

## How it works

```
MasaRentals.pdf  ──►  parse.py  ──►  listings.json  ──►  build.py  ──►  docs/index.html
   (live, weekly)      (pdfplumber,       (structured        (injects JSON        (self-contained
                        column-aware)      listing data)       into template)      static page)
```

- **`parse.py`** — downloads the PDF and turns it into structured records
  (type, bedrooms, baths, location, rent, utilities included, phone numbers,
  description). Column boundaries are pinned to the PDF's fixed layout.
- **`build.py`** — runs the parser against the live PDF (or a local `--pdf`),
  checks the result with `checks.py`, writes `listings.json`, and injects it
  into `site/template.html` to produce `docs/index.html`.
- **`checks.py`** — the weekly data-quality gate. *Hard* failures abort the
  build without touching any file (fewer than 60 listings, count down >30%
  from last week, <95% with a location, <90% with a phone, a whole property
  type missing). *Soft* problems (an unexpanded abbreviation like "Westgt.",
  run-together words, many empty descriptions) print `WARN:` lines and still
  publish, so you know which rule to add to `parse.py`.
- **`site/template.html`** — the page: client-side search, filters (type,
  bedrooms, max rent, utilities, furnished, short-term), sort, light/dark.
  All data is embedded; no network calls at runtime.

## Rebuild locally

```bash
python3 -m pip install -r requirements.txt  # use -m pip, not a bare `pip`:
                                             # on some images `pip` and `python3`
                                             # resolve to different interpreters
python3 build.py                 # fetch the live PDF and rebuild
python3 build.py --pdf some.pdf  # use a local PDF instead
open docs/index.html
```

## Tests

```bash
npm run test:all          # everything below
npm run test:search       # node --test tests/search.test.js
npm run test:locations    # python3 -m unittest discover -s tests
```

Location names are normalised by two tables at the top of `parse.py`
(`PLACE_NAMES` for whole names like "Club at Jackson 21", `ABBREVIATIONS` for
things like "TR" -> "Toms River"). Add a line there when a new abbreviation
shows up, and a case in `tests/test_locations.py`.

The search/filter logic lives in `site/search-core.js` (pure functions, no DOM),
which `build.py` inlines into the page. `tests/search.test.js` (38 tests, Node's
built-in runner, no dependencies) covers text search, every filter, sorting,
the real `listings.json`, and the code actually shipped in `docs/index.html`.

## Weekly auto-refresh

A scheduled Claude Code cloud agent runs every Wednesday just after midnight ET.
It checks out this repo, runs `build.py`, and republishes the Artifact.
See [`ROUTINE.md`](ROUTINE.md) for the exact agent prompt and schedule.

Published Artifact: https://claude.ai/code/artifact/b8837b56-6782-4202-b3d7-c8db84ff1014

## Notes

- The `src/` and `public/` folders are an unused Create React App scaffold from
  when the project was first created. The live site is the static `site/` build.
- Parsing is best-effort against a PDF that is laid out for print. Occasional
  quirks (a missing location, a run-together word) are expected; the original
  PDF is the source of truth.
