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

## Streets ("sort by nearest this street")

`streets.json` holds every named street in Lakewood Township, plus (owner: only the Jewish neighborhoods of the
surrounding towns) the streets within 0.9 mile of each place in `places.json` that lies outside Lakewood, as simplified lines (OpenStreetMap, ODbL; the
page credits "OpenStreetMap contributors"). `build.py` embeds it in the page; the search box suggests any street,
sorts by distance to the street's whole line, and offers intersections ("clover & ocean").
- Rebuild (streets rarely change; the weekly routine does not do this): `python3 tools/build_streets.py --fetch`
  (about 25 minutes, one polite request per map tile; also fetches town borders and the state routes) or `--cache DIR`
  to rebuild from saved tiles. After adding a place outside Lakewood to `places.json`, rebuild so its streets are covered.
- Town labels come from the real borders in `data/town_borders.json`; suggestions list Lakewood's streets first.
- Owner-defined neighborhoods win: a street with the same name as one (Clover Street / "Clover") is kept in the
  data, flagged, so intersections work, but it is not suggested as a second entry.
- It was spot-checked against Google Maps on 2026-11-22 (six streets within 0.003 mi; tests record it). These are
  street lines only; the places listings are pinned to still come from `places.json` (Google-checked).

## Not every listing location is a neighbourhood

A vague phrase in a listing ("Prime Jackson Area", "55+Community", "Lakewood Area") is not a neighbourhood. It may get a
guessed pin in `places.json` so its listing still sorts by distance, but set `"hide": true` on that entry so it is never
offered in the "Near" suggestions (`geo.picker_entries` skips hidden entries; listings still resolve to the pin).

## Search words (site/search-core.js)

- `CONCEPTS` are groups of words that mean the same in these listings (boy = bochur = bachur = guys = men ...). Add a
  line to teach the search a new group; words match as whole words, and typos/spellings (6+ letters) are forgiven.
- **55+ is a search term and a one-tap filter**, not a neighborhood: "55+", "55 plus", "over 55", "senior", "active adult"
  all normalise to `55+` (`normalizeQuery`); the "55+" chip in the search bar sets `S.age55`; typing a 55+ word offers
  "55+ communities" as a topic suggestion. A listing counts as 55+ if it says so or is in the Fairways / Enclave.

## Abbreviations in descriptions (abbrev.py)

Masa U'Matan charges by the word, so descriptions are shorthand ("Av. imm.", "furn. apt.", "lg. bkyd.", "WD", "SS appliances").
`abbrev.expand` spells them out in `parse.clean_comment` (one left-to-right pass: it drops the abbreviation's own full stop
mid-sentence, keeps it at a sentence end, and follows the original's capitals). Abbreviations with two meanings look at the
neighbouring words (Sep. 1 / Sep. kitchen, 10 min. walk / 3 mo. min., Inc. wifi / incl.). Add a new abbreviation as a rule
in `RULES` plus a test in `tests/test_abbrev.py`; check the real descriptions after a change (the weekly build warns on
odd long words, but not on abbreviations nobody has added yet).

## Shuls ("near this shul")

`shuls.json` lists the synagogues / shuls / batei medrash within ~9 miles of Lakewood (223 on 2026-11-22), harvested from
Google Maps search results (coordinates are Google's own place points, so they need no extra check). The search box suggests them
by name, with their street and town ("shul · 958 E County Line Rd · Lakewood"), Lakewood first, and sorts by distance to the shul
(the "Within" menu goes down to ¼ mile). Spelling variants (bais/beis/beit, medrash/midrash) are folded together in
`search-core.js` (`SHUL_SPELL`); generic words ("shul", "congregation") are ignored when something specific is typed.
- Names are shown as people say them: "Congregation"/"Cong." is dropped (`geo.spoken_shul_name`), nobody says it.
- A shul that is also a neighbourhood shows **once**, as the neighbourhood ("Kol Shimshon", "Lutzk", "Westgate", ...): `geo.merge_shuls`
  folds a shul into the same-named neighbourhood within 0.3 mi (words every shul name has - Bais Medrash, Shul, of - are ignored) or the
  `"area": "<picker name>"` field in shuls.json. The neighbourhood keeps its pin and gains the shul's name as another spelling; the drop-down
  says "area & shul". A street is never merged (Spruce Street Shul stays a shul).
- BMG buildings are shuls too (owner: public places used as a shul, and people say them as an area): five entries added by hand, all
  findable by typing "BMG"; the old `bais shalom` and `yeshiva` (BMG) places are the same places and are merged in.
- Kollels stay in the list (owner, 2026-11-22: keep): Google files them under synagogue and each has a beis medrash.
- Left out on purpose: yeshiva / Beth Medrash Govoha school buildings, churches and messianic "synagogues", halls, shops.
  A `"hide": true` entry is dropped by `geo.load_shuls`; `"aka": [...]` adds other spellings.
- To refresh: run the Google Maps searches ("synagogue", "shul", "beis medrash", "minyan") over a grid of map tiles in the built-in
  browser (a search shows ~120 results, so use zoom-16 tiles; read each result's `!3d<lat>!4d<lng>`), merge by name+point.
  Not done by the weekly routine.
- There is deliberately no "closest shul" tag on each listing: pins are neighbourhood-level, and in Lakewood nearly every
  listing is within a few blocks of a dozen shuls, so the tag would say nothing. Search "near <shul>" instead.

## The layout and the map (owner picked design option A + Table + phone sheet, 2026-11-22)

Design canvas with the options: https://claude.ai/artifact/Aj253LKTFAR3uJnCsaatTq (First version, Current, Options A/B/C, phone).
- **Computer:** one slim sticky top bar: "Lakewood NJ Area Rentals", the search box, 55+, filter drop-downs (Type, Bedrooms, Max rent,
  Landlord pays, More), a **Price listed** pill and no "Source" button (owner removed it, 2026-11-22). The unofficial-site notice, links, OpenStreetMap credit, Masa U'Matan's phone number and the
  light/dark switch are a small fine-print block at the end of the cards / table (`#fineprint`); there is no masthead or footer.
  Below it the map on the left (sticky) and cards on the right; a **Cards | Table** switch. Table = dense rows (where, type, bd, ba,
  rent, notes, call) with a neighbourhood list with counts on the left; clicking a row opens its full text and a "Show on map" button.
- **Cards:** big bd/ba numbers, the rent or "Ask for price" (52% of listings give no rent: 123 of 237), neighbourhood + type, a quiet
  outline call button (not a green block). The selected card shows its whole description.
- **Map pins:** a rent pill ("$1.8k") for a priced listing, a hollow dot when no rent is listed, a number where several listings share a spot
  (popup lists them); zoomed out, pills shrink to dots. Always labelled "pins are approximate"; the dashed circle (`uncertaintyMiles`:
  neighbourhood 0.15 mi, two places averaged = half their spread + 0.1, town only = 1 mi) shows how unsure the selected spot is.
- **Phone:** no masthead; the map fills the screen under the search row and the listings are a bottom sheet (peek / half / full; drag
  the handle or tap it). Tapping a card shows it on the map (the map is padded so the pin is above the sheet).
- **Never a map per card** (tried, too zoomed in). Selecting a card moves the map to its neighbourhood in its surroundings (at least ~1.5 mi).
- **Shuls are markers on the map** (owner, 2026-11-23): all of `shuls.json` (payload field `shulpins`, including shuls merged into a neighbourhood in the
  drop-down) as small star markers from zoom 14, names from zoom 16; tapping one offers "Rentals within ½ mile" (sets the Near chip and the radius). They are
  our own data, so they do not depend on the basemap showing landmarks. Legend says "✡ shul".
- Basemap: standard OpenStreetMap tiles. CARTO's free Voyager/Dark Matter tiles were tried and now stamp "API KEY REQUIRED" on the map (needs an account key);
  Google/Mapbox/MapTiler/Stadia also need a key. A keyed provider (e.g. MapTiler or Stadia free tier) is the way to a Google-like look later.
- Leaflet 1.9.4 (script from cdnjs with SRI; `site/leaflet.css` inlined by build.py because artifact pages may only load stylesheets from
  Google Fonts) + OpenStreetMap tiles. The private Artifact page blocks tile images, so there the map falls back to streets.json lines +
  neighbourhood names (`streetFallback`); the public GitHub Pages site gets the real map. Google Maps cannot show many pins without an
  API key and billing, and cannot be embedded inside an artifact.
- The page script uses `L` for the listings, so Leaflet is read as `LF` (set right after the script tag). Don't rename.
- If the map script is blocked the list takes the full width (`nomap`).

## Typing a place IS a location search (owner, 2026-11-24)

`LakewoodSearch.placeIntent(text, picker, streets, shuls)` decides what the typed words mean. If they name a neighbourhood, shul, street or
intersection (3+ letters, a real prefix match, the first dropdown suggestion), the page sorts **every listing nearest-first** from it at once
(nothing is filtered out), shows "Nearest first to X . press Enter to keep it . search the word instead" under the search box, and puts the
spot on the map; Enter or a click keeps it as the "Near" chip. Otherwise the words stay a keyword filter. Rules:
- Words that mean something in a listing (pool, boy, basement, 55+), typo matches, and the bare words shul / minyan stay keywords. A neighbourhood or
  shul wins over a street. A street word that fits several equally good streets (forest, birch) stays a keyword **unless** it is in
  `data/preferred_streets.json` (owner-curated: "forest" = Forest Avenue, "birch" = Birch Street, both Lakewood): then that street is first in the
  drop-down and the "near" street at once; the other streets stay below it. Add a word there when the owner names the street people mean.
- **A typo of a place is that place** (owner, 2026-11-24): "foreset" = Forest Avenue (not Sterling Forest: a name's own first word beats a word in the
  middle, and `preferred_streets` also catches typos), "spruse street", "kol aryh", "jak" = Jackson. The note then reads "Did you mean X?". Typos of words
  the listings use (furnishd, basment) stay keywords.
- "raintree pool" = Raintree (sort) + "pool" (filter); the place can come first or last. A last dropdown row, "Search the listings for the
  word ...", and the "search the word instead" link switch a place word back to a keyword filter.
- Once a "Near" chip is set, typing is a keyword filter again.
- **"yeshiva" on its own is "BMG"** (owner, 2026-11-24): the same drop-down and the same near-BMG sort (`WORD_FOR_PLACE` in search-core.js).
- **BMG** alone = the campus between 6th and 7th St (place "BMG", first in the list). The other buildings go by their own names: Beis Aharon
  (10th St), Beis Shalom (9th St), Forest Beis Medrash (Forest Ave), Princeton Beis Medrash (southeast corner of Princeton Ave and 7th St;
  the owner's description, "I believe", Google Maps has no listing, so the pin is approximate).

## Search box must say it finds shuls

The placeholder reads "Neighborhood, street, shul or keyword..." ("Area or shul..." on a phone), the empty focused box lists what can be
searched (neighborhood, street/intersection, shul, any word; picking an example types it), and typing just "shul"/"synagogue"/"minyan" shows
"Type a shul's name". Keep this when the search box changes.
