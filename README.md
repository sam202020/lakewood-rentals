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
- **`site/template.html`** + **`site/search-core.js`** - the page: search, filters, sort, map, light/dark. `build.py`
  writes a complete HTML document; the listing data is embedded with `<` escaped, because listing text comes from
  advertisers. At runtime the page loads Leaflet (cdnjs, integrity-checked), OpenStreetMap map pictures, Google Fonts
  and, on the public domain only, the GoatCounter visit counter.

The public site is <https://lakewoodnjrentals.com> (GitHub Pages serves `docs/`).

## Rebuild locally

```bash
python3 -m pip install -r requirements.txt  # use -m pip, not a bare `pip`:
                                             # on some images `pip` and `python3`
                                             # resolve to different interpreters
python3 build.py                 # fetch the live PDF and rebuild
python3 build.py --pdf some.pdf  # use a local PDF instead
open docs/index.html
```

## Map coordinates ("Near" / closest-to-me)

Locations are neighborhoods and streets, not addresses, so each listing is placed
at the middle of the place(s) it names (`geo.py`). Coordinates live in
`places.json`, which you can edit by hand (set `lat`/`lng` and `"source": "manual"`;
manual entries are never overwritten). `tools/geocode_places.py` fills in new names
from OpenStreetMap; run it locally when the weekly report warns that place names
are missing. Listings that can't be placed still show, but sort last by distance.
Visitors can sort by distance from a neighborhood or from their browser location
(which never leaves their device).

## Tests

```bash
npm run test:all          # everything below
npm run test:search       # node --test tests/search.test.js (also runs python3 for the sample week)
npm run test:locations    # python3 -m unittest discover -s tests
RENTAL_PDF=/path/to/MasaRentals.pdf npm run test:all     # also checks the parser on a real PDF
```

Tests never depend on this week's list: those that need real listings use the frozen week in `tests/fixtures/week.json`
(`tests/week_data.py` builds the page data from it with the current code). The weekly list itself is checked by
`checks.py` during the build. A test that reads `listings.json` would pass one week and block the next refresh.

## Notes

- There are no npm dependencies: `package.json` only names the test scripts.
- Parsing is best-effort against a PDF that is laid out for print. Occasional quirks (a missing location, a
  run-together word) are expected; the original PDF is the source of truth.
