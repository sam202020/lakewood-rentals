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
