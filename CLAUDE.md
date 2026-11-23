# Lakewood NJ Area Rentals - notes for Claude

Static site built from Masa U'Matan's weekly rental PDF. See README.md and ROUTINE.md for the pipeline.
Tests: `npm run test:all` (Node search tests + Python tests). Build: `python3 build.py`.

## Places and map coordinates: always check Google Maps

Whenever a place is added to or changed in `places.json`, **check it on Google Maps first**.
Never ship a Nominatim/OpenStreetMap first hit unchecked; they were repeatedly wrong
(Raintree in Freehold, Locust Grove near Asbury Park, Route 9/70/88 sharing one point, ...).

- Open `https://www.google.com/maps/search/<name>+Lakewood+NJ` in the built-in browser and read
  the point from the loaded URL (`!3d<lat>!4d<lng>`). For intersections search `A & B`.
- Save it with `"source": "manual"` and a `note` saying where it came from. Manual entries are
  never overwritten by `tools/geocode_places.py`.
- If Google finds nothing or several candidates, ask the owner instead of guessing, and mark
  anything approximate (`APPROXIMATE:` in the note).
- Owner corrections (local knowledge) beat both Google and OSM.
- Sanity-check each point is near Lakewood (`geo.plausible`), and that "Foo" and "Foo St" that
  are the same street have the same coordinates (the drop-down merges them).
- Add or extend a test in `tests/test_geo.py` for anything the owner corrected.

The weekly cloud routine cannot do this (no browser): it only prints `WARN` lines for unknown
names. Resolve those in a local session with the Google Maps check.

## Addresses are never neighbourhoods

A street address ("957 W. County Ln.", "22 Enclave Blvd.") must never appear in the "Near" suggestions or
be treated as a place. `geo.picker_entries` drops anything that `geo.looks_like_address`, and the build prints a
`WARN` for every listing whose location is an address. When one shows up: find the neighbourhood it lies in
(nearest named neighbourhoods on the map, plus any hint in the listing text), **confirm it with the owner**, then
give the address entry that neighbourhood's coordinates and set `"neighborhood": "<place key>"` on it (that silences the
warning). The card still shows the address from the PDF.

## The PDF parser (parse.py)

The PDF is a table of ruled cells. `parse()` finds each listing's row from the drawn cell rectangles
(`row_cells`) and takes every word whose vertical centre lies inside that row (`parse_row`). Do not go back to
guessing listing boundaries from the code text: codes come with the type letters missing or a junk prefix
("CfHH1114_932:15"), the bedroom digit glued on ("..._1049:103"), type letters on a separate line, phone numbers
shattered into single characters or glued to the next word, and ad banners that carry phantom codes.
`_parse_page_by_text` is only a fallback for a page with no cell rectangles.

Rules (owner, 2026-11-22):
- **Every listing in the PDF has a phone number. A listing without one is always a parser bug**, never a
  property of the listing. `checks.py` warns by name and fails the build under 98%. 7-digit local numbers
  ("905-0200") are stored as `732-905-0200`.
- Row count check: `python3 build.py` prints a `NOTE` for every ad banner it leaves out, so a missing listing
  shows up as a missing row, not silence. Nov. 18, 2026 PDF: 244 row bands = 237 listings + 7 ad rows (6 banners + the "FREE" Hachnosas Orchim entry, which the owner says is an ad).
- After changing the parser run it on the real PDF too:
  `RENTAL_PDF=/path/to/MasaRentals.pdf python3 -m unittest discover -s tests`
  (every listing must have a phone, a type and bedrooms; ids unique).
- When the weekly warnings show a new oddity, add the real row as a test in `tests/test_parser.py`.
