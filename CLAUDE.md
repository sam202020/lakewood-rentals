# Lakewood NJ Area Rentals - notes for Claude

Static site built from Masa U'Matan's weekly rental PDF. See README.md and ROUTINE.md for the pipeline.
Tests: `npm run test:all` (Node search tests + Python tests). Build: `python3 build.py`.

## Working rules

- `python3 build.py` writes the live files (`docs/`, `listings.json`, `data/neighborhoods_seen.json`). Before building with `--pdf`,
  compare that PDF's date with `list_date` in `listings.json`: an older list silently overwrites newer data. Revert test rebuilds.
- `business/` (domain, hosting, SEO and monetization plans) is local and untracked. The repo is public, so never commit it
  (no `git add -A` in a local session). Fresh clones and the cloud routine do not have it.

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
warning and counts the listing under that neighbourhood in the lists). The card still shows the address from the PDF.

## The PDF parser (parse.py)

The PDF is a table of ruled cells. `parse()` finds each listing's row from the drawn cell rectangles
(`row_cells`) and takes every word whose vertical centre lies inside that row (`parse_row`). Do not go back to
guessing listing boundaries from the code text: codes come with the type letters missing or a junk prefix
("CfHH1114_932:15"), the bedroom digit glued on ("..._1049:103"), type letters on a separate line, phone numbers
shattered into single characters or glued to the next word, and ad banners that carry phantom codes.
`_parse_page_by_text` is only a fallback for a page with no cell rectangles.
A code can also lack its underscore ("RCF916:9", `CODE_BARE`), and a few rows print only the type letter with no code at all (such a row has no
issue number, so it cannot be dated). Typos in the list that the owner asked to correct live in `DESCRIPTION_TYPOS` (narrow, one wording each:
"Internet included. No contact" is "No contract").

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

## "Jackson" / "Toms River" alone = the Jewish area there (owner, 2026-11-24)

A listing that names only a town is not pinned at the township centre (Jackson's is far west of where the community is). `geo.town_centers`
averages the listings that name a place inside that town (or, with fewer than 3, the named places in `places.json`), and `geo.apply_town_centers`
moves the town-only listings there (Jackson, Toms River, Howell, Manchester, Brick; not Lakewood). The "Jackson", "Howell"... entries in the
"Near" drop-down use the same point, and the dashed circle is as wide as that area (`geo_area_miles`, 0.5 to 1.5 mi). It is recomputed every
build, so it follows the week's listings. Verify the result against Google Maps when it looks off.

## Heritage Point (Howell)

"Howell / Heritage Pt." is pinned at Google Maps' Heritage Dr, Howell 07731 (place `heritage pt`, shown as "Heritage Point", also "Heritage Drive"). The owner is
not sure whether the neighbourhood is called Heritage Point or Heritage Drive; Google has no "Heritage Point". Streets around it were added to `streets.json`.

## Not every listing location is a neighbourhood

A vague phrase in a listing ("Prime Jackson Area", "Lakewood Area") is not a neighbourhood. It may get a guessed pin in
`places.json` so its listing still sorts by distance, but set `"hide": true` on that entry so it is never offered in the
"Near" suggestions (`geo.picker_entries` skips hidden entries; listings still resolve to the pin). When the owner says
where it belongs, add `"neighborhood": "<place key>"` and its listings are counted there in the lists.
- **"Prime Jackson" is Jackson** (owner, 2026-11-26): listed under Jackson and placed exactly like a plain "Jackson"
  listing, at the middle of Jackson's Jewish area (`"town_center": "Jackson"` on its entry). Never shown by that name.
- **NPGS** (owner, 2026-11-26) means the little neighbourhood behind the NPGS store ("NPGS - Jackson" on Google Maps,
  2080 W County Line Rd), near Brookwood 1.
- **55+** (owner, 2026-11-26): the lists have one row, "55+ Communities (Fairways / Enclave)", pinned midway between the
  two. The Fairways, the Enclave, the Enclave address and a vague "55+Community" are counted in it
  (`data/neighborhood_also.json`). It is `"list_only": true`: never a typed suggestion, where "55+" offers the 55+ filter.
- Description words that slip into a location ("KITCHENETTE. PRIVATE") are never places: no `places.json` entry
  (`geo.looks_like_description`; the geocoding tool skips them).

## The Neighborhood and Street lists (owner, 2026-11-26)

`LakewoodSearch.listGroups` feeds the search box's "Neighborhoods" and "Streets" browse lists and the Table view's side
list (neighbourhoods only). It takes every name in `DATA.neighborhoods` (this week's plus `data/neighborhoods_seen.json`)
and each listing's first `/`- or comma-separated name and `areas`, matches each name to a place with the search
(`placeForName`), and merges names that mean the same place.
- **Every listing must be in at least one of the two lists.** A name that matches nothing is silently dropped, so
  `build.py` prints a `WARN` naming such listings (`tools/check_lists.js`, needs Node). Fix them with a place, another
  spelling or one of the rules here.
- A neighbourhood with no listing this week stays in its list with "0 listings". `build.py` writes the (only growing) set
  of names back to `data/neighborhoods_seen.json`.
- A name ending in Street, Road, Court, ... goes in the Street list. **Streets people also mean as an area go in both**
  (`data/area_streets.json`: Medina Road, and Ridge shown as "Ridge"). Add one only when the owner names it.
- **Abbreviations** (`placeTokens`): Rd, Ct, Ln, Rt are read as Road, Court, Lane, Route, and "County Ln" as County
  Line, both when typed and when matching list names.
- **Another spelling is the place**: a `places.json` entry's `"aka"` is used both by the search and to put listings on
  the map. "Heart of Ridge" is Ridge (the middle of Ridge, Ridge Ave at Nowlan Pl) and "Wyndham 2" is Wyndham; neither
  gets its own entry in the lists.
- "Laurel" is Laurel Avenue and "Manetta" is Manetta Avenue (`data/preferred_streets.json`, see "Typing a place").

## Search words (site/search-core.js)

- `CONCEPTS` are groups of words that mean the same in these listings (boy = bochur = bachur = guys = men ...). Add a
  line to teach the search a new group; words match as whole words, and typos/spellings (6+ letters) are forgiven.
- **55+ is a search term and a one-tap filter** (plus one row in the neighbourhood list, see above): "55+", "55 plus", "over 55", "senior", "active adult"
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

`shuls.json` lists the synagogues / shuls / batei medrash within ~9 miles of Lakewood (229 on 2026-11-26; 18 of them show in the drop-down as their neighborhood), harvested from
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
- **Cards:** big bd/ba numbers, the rent or "Ask for price" (about half of listings give no rent), neighbourhood + type, a quiet
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

`LakewoodSearch.placeIntent(text, picker, streets, shuls, preferred)` decides what the typed words mean. If they name a neighbourhood, shul, street or
intersection (3+ letters, a real prefix match, the first dropdown suggestion), the page sorts **every listing nearest-first** from it at once
(nothing is filtered out), shows "Nearest first to X . press Enter to keep it . search the word instead" under the search box, and puts the
spot on the map; Enter or a click keeps it as the "Near" chip. Otherwise the words stay a keyword filter. Rules:
- Words that mean something in a listing (pool, boy, basement, 55+), typos of such words, and the bare words shul / minyan stay keywords (a mistyped
  place name counts as that place, see below). A neighbourhood or shul wins over a street. A street word that fits several equally good streets (forest, birch) stays a keyword **unless** it is in
  `data/preferred_streets.json` (owner-curated: "forest" = Forest Avenue, "birch" = Birch Street, both Lakewood): then that street is first in the
  drop-down and the "near" street at once; the other streets stay below it. Add a word there when the owner names the street people mean.
- **A typo of a place is that place** (owner, 2026-11-24): "foreset" = Forest Avenue (not Sterling Forest: a name's own first word beats a word in the
  middle, and `preferred_streets` also catches typos), "spruse street", "kol aryh", "jak" = Jackson. The note then reads "Did you mean X?". Typos of words
  the listings use (furnishd, basment) stay keywords.
- **A keyword never hides the rest of the list** (owner, 2026-11-24): `LakewoodSearch.searchAll` returns `matches` (every filter passes and the words are
  mentioned) and `others` (every filter passes, the words are not). The page shows "N listings mention 'pool'", the matches, a divider "N other
  listings", then the others (each group in the chosen sort; the map dims the others' pins and fits to every matching pin (the "core of Lakewood" view that ignores far-out towns is only for 60+ pins), but never closer than zoom 14, about 3 miles across, so the surroundings stay in view). If nothing mentions the
  words it says so and shows the whole list. The other filters (type, beds, rent, ...) stay strict.
- **Keyword suggestions** (owner, 2026-11-24: "pool" is not Liverpool): typed words match the start of a word in a name, never the middle. When the word is in the
  listings the drop-down offers it first with its listing count ("pool . keyword . 15 listings") and related words that pick out different listings
  ("heated pool . 3 listings"), then only places that really start with it. A related word with the same listings as one already offered is left out.
- A typo only counts as a place when it is a real misspelling of the name (edit distance), not merely a similar sound (so "zzzzqq" is not Zackery Court).
- "raintree pool" = Raintree (sort) + "pool" (filter); the place can come first or last. A last dropdown row, "Search the listings for the
  word ...", and the "search the word instead" link switch a place word back to a keyword filter.
- Once a "Near" chip is set, typing is a keyword filter again.
- **"yeshiva" on its own is "BMG"** (owner, 2026-11-24): the same drop-down and the same near-BMG sort (`WORD_FOR_PLACE` in search-core.js).
- **BMG** alone = the campus between 6th and 7th St (place "BMG", first in the list). The other buildings go by their own names: Beis Aharon
  (10th St), Beis Shalom (9th St), Forest Beis Medrash (Forest Ave), Princeton Beis Medrash (Google Maps: "BMG Bais Shmuel", Princeton Ave & 7th St; also found as Bais Shmuel).

## Search box must say it finds shuls

The placeholder reads "Neighborhood, street, shul or keyword..." ("Area or shul..." on a phone). The empty focused box lists the kinds of search
(Neighborhood, Street or intersection, Shul, Keyword; no "A", and no Chabad in the examples because nobody searches it). **Clicking one opens the list
to choose from**, not an example typed for you: neighborhoods with listings (merged by the place they resolve to, so Hearthstn. and Hearthstone are one),
streets and intersections with listings, all shuls (Lakewood first), or common words with their listing counts. Typing just "shul"/"synagogue"/"minyan"
shows "Type a shul's name". Keep this when the search box changes.

## Custom domain: keep `docs/CNAME`

The public site is **https://lakewoodnjrentals.com** (owner registered it; set in the repo's Pages settings 2026-11-26). GitHub Pages
reads the domain from `docs/CNAME`; never delete, move or rewrite that file (`build.py` writes `docs/index.html`, `docs/sitemap.xml` and
`docs/robots.txt`; tests in `tests/test_checks.py` check that `CNAME` survives a build). DNS is at Cloudflare: four `A` records to GitHub Pages (185.199.108-111.153) and `www` CNAME to
`sam202020.github.io`, all "DNS only". The old `sam202020.github.io/lakewood-rentals` address redirects to the domain.

## Search engines and link previews (seo.py)

`build.py` puts `seo.head_tags()` (description with the listing count and list date, canonical, Open Graph and Twitter preview) at
`<!--__SEO__-->` in the template and writes `docs/sitemap.xml` (lastmod = the rental list's date) and `docs/robots.txt`. The preview
picture `docs/og.png` is committed; redraw it with `python3 tools/build_og_image.py` (on a Mac) after changing its words. The domain is
`seo.SITE_URL`, which a test ties to `docs/CNAME`. Next steps (neighbourhood and topic pages) are in
`business/domain-hosting-seo-plan.md` §5.3.

## Owner neighbourhood calls (2026-11-26)

- **Chestnut** and **Locust** are streets, but people mean them as neighbourhoods ("near Chestnut"): each is its own neighbourhood entry,
  never grouped under Chestnut Acres or Locust Grove.
- "Near Chateau" is **Chateau Park**. "Club at Jackson 21" / "Club 21 Jackson" are **Jackson 21**.
- **Oak Meadows**: 19 Hilton Dr and its cul-de-sac, off Oak St near Route 9 and Oak & Vine. **The Vineyards**: Jackson, near 75 Tuscany Dr.
- A place entry's `label` overrides its `name` in the drop-down: remove it when renaming.
- **Albert Run** is at and around 1 Radiant Hill; people also call it **Sims**. Both are neighbourhoods, essentially one area. A listing in
  either is listed under Albert Run, Sims **and** Albert: owner rule in `data/neighborhood_also.json` (`geo.listing_areas` puts `areas` on the
  listing; `originMiles` treats such a listing as "right here" for any of them; the lists count it under each).
- **One grouping for the neighbourhood lists** (owner, 2026-11-26): see "The Neighborhood and Street lists". Never group the Table view's side
  list (biggest first) by the PDF's raw wording again; clicking a name there sorts by that neighbourhood, the same as picking it in the search box.

## Table view: column headers sort (owner, 2026-11-26)

Where, Type, Bd, Ba and Rent headers are buttons (`nextColumnSort`): the first click sorts the way people usually want (A-Z, most bedrooms/baths,
cheapest rent), the second reverses, the third returns to the normal order (nearest first when a "Near" place is set). **Type** has four kinds, so each
click stacks the next one on top (Apartment, House, Room, Townhouse; the rest follow alphabetically, wrapping; "Other" last), and a fifth returns to
normal; the header shows which type is on top. A listing without the value
(no rent, no bath count) stays last in either direction. Notes and Call are not sortable. The Sort menu offers the same modes and stays in step.

## Names in the neighbourhood list

Only real places: description words that slip into a location ("KITCHENETTE. PRIVATE") are never kept (`geo.looks_like_description`), and a variant
such as "Outside Brookwd 1" counts under its neighbourhood (Brookwood 1, through its `aka` in places.json) - never as "outside ..." of its own.

## Default order is newest first (owner, 2026-11-26)

The number before the colon in a listing's code (`11TT78_1057:7` -> 1057) is the Masa U'Matan issue the ad was placed in: it stays while the ad runs and
rises about one a week (checked on the Aug. 26, Nov. 18 and Nov. 25 lists). `issueNumber` / `newestIssue` (highest number at least 3 ads share) /
`newestFirst` in search-core.js: newest issue first, list order within an issue, ads without a code number last; ties in every other sort are newest
first too (in nearest-first, listings at the same spot that name the picked place come before the others, then newest). This week's ads get a "New this week" tag (cards) / "New" (table). Nothing is stored between weeks, so the weekly routine needs no change.
If the codes ever change shape, the tags disappear and the order falls back to the list order: check this when that happens.

## Location spelling

`parse.tidy_location` spells out abbreviations in location names; "Brookwd" is "Brookwood" and "Outside Brookwood 1" is "Brookwood 1" (owner).

## Visit and call-tap counts (owner approved, 2026-11-26)

Counting is **on** (since 2026-11-26): site code `lakewoodnjrentals`, dashboard <https://lakewoodnjrentals.goatcounter.com>.
Cookie-free GoatCounter. The site code (the `xxxx` of `xxxx.goatcounter.com`) goes in `data/analytics.json`; empty = nothing is counted and the
page says nothing about counting. `build.py` puts it in the page (`counter`). Rules (tests in `tests/search.test.js`, `tests/test_counter.py`):
- Counted only on `lakewoodnjrentals.com` (`countsHere`): local copies, test browsers and the private Artifact page never count. A new
  domain must be added to `PUBLIC_HOSTS` in `search-core.js`.
- **The owner does not want to be counted:** a device that opens the site with `#nocount` stores GoatCounter's `skipgc` flag and is never counted
  (`#count` undoes it; private windows and cleared browser data forget it). Never test the live site in a way that counts.
- Events: one "Call tap" per tap on a call link (cards, table, map pop-ups), filed as `call: <area>` (`callArea`). Never send a phone number, a
  street address, names or search text. A tap is not a completed call.
- `count.v5.js` is pinned with an integrity hash; if GoatCounter changes the file the browser refuses it and counting stops silently.

## The built page and the tests (launch review, 2026-11-26)

- `build.render_page` writes a full HTML document (doctype, `lang`, favicon `docs/favicon.svg`, `h1.brand`, hidden but present on phones). The
  template is split at `<!--__BODY__-->`; keep that mark.
- **Advertiser text is untrusted.** `build.embed_json` writes every `<` in the data as `\u003c` so a description cannot close the data block.
  Never embed data another way, and keep using `esc()` for anything put into `innerHTML` (`tests/test_page.py`).
- **Tests must not depend on this week's list** (it broke the weekly refresh once). Use `week_data.week()` (Python) or `pagePayload()` (Node), which
  build from `tests/fixtures/week.json`. Data quality of the live list belongs in `checks.py` (warn, or abort the build).

## Open items (as of 2026-11-26)

Ask the owner before acting on any of these.
- **Weekly routine:** it has not yet finished a run without help. A supervised manual run (it publishes) was proposed before the next
  scheduled one, Wed Dec 2 just after midnight New York time.
- **Google Maps data:** the launch review flagged that Google's terms may not allow collecting the shul list this way, shown on a
  non-Google map. Choices: rebuild from OpenStreetMap plus owner corrections (recommended), ask a lawyer, or accept the risk.
  Undecided; ask before harvesting shuls again.
- **Masa U'Matan:** talk to them before promoting the site or taking money.
- **UI options** (D1 desktop and P1 phone recommended, nothing built; the layout above stands):
  <https://claude.ai/artifact/CEpEJsSekG2xFySqZbkjq9>
- **Fairways in the lists:** a listing that says "Fairways" is grouped (and typing "fairways" sorts) as the street
  Fairways Boulevard, not the Fairways neighbourhood. Ask the owner whether to change it.
- **Pins to confirm:** "Cov.:Princeton" read as Coventry; "Tamarind Park" pinned at Tamarind Rd.
- **Owner to-dos:** check the WhatsApp link preview; add the site to Google Search Console and submit the sitemap; open the site with
  `#nocount` on each own device; answer the monetization plan's questions.
- **Later:** neighborhood tags on listings (reminder 2026-12-07), paid map provider (domain plan checklist 11), neighborhood and topic
  pages for search engines (domain plan §5.3), a "page not found" page.
