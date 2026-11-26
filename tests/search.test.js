// Tests for the page's search/filter logic.  Run:  node --test tests/
// No dependencies: uses Node's built-in test runner (Node 18+).
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const S = require("../site/search-core.js");
const ROOT = path.join(__dirname, "..");

// Real listings come from a frozen week (tests/fixtures/week.json), built with the current code: never from listings.json
// or docs/index.html, which change every Wednesday and would make the weekly refresh block itself.
const WEEK = require("node:child_process").execFileSync("python3", [path.join(__dirname, "week_data.py")], { encoding: "utf8", maxBuffer: 50e6 });
const pagePayload = () => JSON.parse(WEEK);

// ---- fixtures ---------------------------------------------------------------
function L(over) {
  return Object.assign({
    type: "Apartment", bedrooms: "2", bedrooms_num: 2, baths: "1", location: "Albert Area",
    rent: 1800, rent_display: "$1,800/mo", utilities_included: [], phones: ["732-555-0101"],
    furnished: false, comments: "Nice apartment."
  }, over);
}
function fixture() {
  return S.enrich([
    L({ id: "a", location: "Raintree", type: "House", bedrooms_num: 4, bedrooms: "4", baths: "2½",
        rent: 3500, comments: "Colonial with backyard. Available immediately.", phones: ["917-731-1537"] }),
    L({ id: "b", location: "Mackenzie Area Toms River", type: "House", bedrooms_num: 5, bedrooms: "5",
        rent: null, rent_display: "Call to discuss", comments: "Great basement. Pool." }),
    L({ id: "c", location: "Club at Jackson 21", type: "Townhouse / Attached", bedrooms_num: 4, bedrooms: "4",
        rent: 3350, comments: "Andrew model. 2-car garage." }),
    L({ id: "d", location: "Arlington", type: "Apartment", bedrooms_num: 1, bedrooms: "1", rent: 1300,
        utilities_included: ["Gas", "Electric", "Water", "Heat"], furnished: true,
        comments: "Furnished Choson/Kallah apt. Short term or long term." }),
    L({ id: "e", location: "Westgate", type: "Room", bedrooms_num: 1, bedrooms: "1", rent: 600,
        utilities_included: ["Water"], comments: "Private room for working men." }),
    L({ id: "f", location: "Ridge Area", rent: 2200, bedrooms_num: null, bedrooms: "",
        comments: "Studio, furnished, weekly rental." })
  ]);
}
function ids(rows) { return rows.map((r) => r.id).join(""); }
function run(over) { return S.search(fixture(), Object.assign(S.defaultState(), over)); }

// ---- derived fields ---------------------------------------------------------
test("bathNum parses whole and fractional baths", () => {
  assert.equal(S.bathNum("2"), 2);
  assert.equal(S.bathNum("2½"), 2.5);
  assert.equal(S.bathNum("3¼"), 3.25);
  assert.equal(S.bathNum("1¾"), 1.75);
  assert.equal(S.bathNum(""), null);
  assert.equal(S.bathNum(undefined), null);
});

test("enrich adds derived fields and keeps list order index", () => {
  const rows = fixture();
  assert.deepEqual(rows.map((r) => r._i), [0, 1, 2, 3, 4, 5]);
  assert.equal(rows[0]._baths, 2.5);
  assert.match(rows[0]._text, /raintree/);
  assert.match(rows[0]._text, /917-731-1537/); // phone numbers are searchable
  assert.equal(rows[3]._furnished, true);
  assert.equal(rows[5]._furnished, true);      // inferred from the comment text
  assert.equal(rows[0]._furnished, false);
});

test("short-term detection covers the wording used in the list", () => {
  const rows = fixture();
  assert.equal(rows[3]._short, true);   // "Short term"
  assert.equal(rows[5]._short, true);   // "weekly"
  assert.equal(rows[0]._short, false);
  const more = S.enrich([
    L({ comments: "Short/long term available." }),
    L({ comments: "$150/night." }),
    L({ comments: "short-term rental" }),
    L({ comments: "Long term only." })
  ]);
  assert.deepEqual(more.map((r) => r._short), [true, true, true, false]);
});

test("tags are derived from comments", () => {
  const tags = (r) => r._tags.map((t) => t[0]);
  const rows = fixture();
  assert.deepEqual(tags(rows[0]), ["Available now", "Backyard"]);
  assert.ok(tags(rows[1]).includes("Pool"));
  assert.ok(tags(rows[1]).includes("Basement"));
  assert.ok(tags(rows[3]).includes("Choson / Kallah"));
  assert.ok(tags(rows[3]).includes("Short-term OK"));
  assert.ok(tags(rows[3]).includes("Long-term"));
});

// ---- default state ----------------------------------------------------------
test("default state matches every listing", () => {
  assert.equal(ids(run({})), "abcdef");
});

test("defaultState returns independent objects (no shared Sets)", () => {
  const a = S.defaultState(), b = S.defaultState();
  a.types.add("House");
  assert.equal(b.types.size, 0);
});

// ---- text search ------------------------------------------------------------
test("search matches location, case-insensitively", () => {
  assert.equal(ids(run({ q: "raintree" })), "a");
  assert.equal(ids(run({ q: "RAINTREE" })), "a");
  assert.equal(ids(run({ q: "Toms River" })), "b");
});

test("search matches the multi-word locations from the PDF", () => {
  assert.equal(ids(run({ q: "club at jackson 21" })), "c");
  assert.equal(ids(run({ q: "mackenzie area toms river" })), "b");
});

test("search matches comments and phone numbers", () => {
  assert.equal(ids(run({ q: "garage" })), "c");
  assert.equal(ids(run({ q: "917-731-1537" })), "a");
});

test("search matches the listing type text", () => {
  assert.equal(ids(run({ q: "townhouse" })), "c");
});

test("multiple search terms must all match (AND), in any order", () => {
  assert.equal(ids(run({ q: "jackson garage" })), "c");
  assert.equal(ids(run({ q: "garage jackson" })), "c");
  assert.equal(ids(run({ q: "jackson basement" })), "");
});

test("blank and whitespace-only queries match everything", () => {
  assert.equal(ids(run({ q: "" })), "abcdef");
  assert.equal(ids(run({ q: "   " })), "abcdef");
});

test("surrounding and repeated whitespace is ignored", () => {
  assert.equal(ids(run({ q: "  toms    river  " })), "b");
});

test("a query with no hits returns nothing", () => {
  assert.equal(ids(run({ q: "zzzzz" })), "");
});

test("search is not tripped up by regex characters", () => {
  assert.doesNotThrow(() => run({ q: "(.*" }));
  assert.equal(ids(run({ q: "(.*" })), "");
});

// ---- type -------------------------------------------------------------------
test("type filter: single and multiple types", () => {
  assert.equal(ids(run({ types: new Set(["House"]) })), "ab");
  assert.equal(ids(run({ types: new Set(["House", "Room"]) })), "abe");
  assert.equal(ids(run({ types: new Set(["Townhouse / Attached"]) })), "c");
});

// ---- bedrooms ---------------------------------------------------------------
test("bedrooms filter is a minimum", () => {
  assert.equal(ids(run({ beds: 4 })), "abc");
  assert.equal(ids(run({ beds: 5 })), "b");
  assert.equal(ids(run({ beds: 1 })), "abcde"); // f has no bedroom count
});

test("listings with no bedroom count are excluded by any bedroom minimum", () => {
  assert.ok(!ids(run({ beds: 1 })).includes("f"));
  assert.ok(ids(run({ beds: 0 })).includes("f"));
});

// ---- rent -------------------------------------------------------------------
test("max-rent filter keeps listings at or under the cap", () => {
  const r = run({ rent: 1800 });
  assert.ok(r.every((x) => x.rent == null || x.rent <= 1800));
  assert.equal(ids(run({ rent: 1300, inclCall: false })), "de"); // exactly 1300 is included
});

test("'call to discuss' listings are shown or hidden by the checkbox", () => {
  assert.ok(ids(run({ rent: 1000, inclCall: true })).includes("b"));
  assert.ok(!ids(run({ rent: 1000, inclCall: false })).includes("b"));
});

test("the slider's top position means no cap", () => {
  assert.equal(ids(run({ rent: S.NO_RENT_CAP })), "abcdef");
  assert.equal(ids(run({ rent: S.NO_RENT_CAP, inclCall: false })), "acdef");
});

// ---- utilities / furnished / short-term ------------------------------------
test("landlord-pays filter requires every selected utility", () => {
  assert.equal(ids(run({ utils: new Set(["Heat"]) })), "d");
  assert.equal(ids(run({ utils: new Set(["Water"]) })), "de");
  assert.equal(ids(run({ utils: new Set(["Water", "Heat"]) })), "d");
  assert.equal(ids(run({ utils: new Set(["Gas", "Heat", "Water", "Electric"]) })), "d");
});

test("furnished-only filter", () => {
  assert.equal(ids(run({ furnished: true })), "df");
});

test("short-term filter", () => {
  assert.equal(ids(run({ shortterm: true })), "df");
});

// ---- combined ---------------------------------------------------------------
test("filters combine with AND", () => {
  assert.equal(ids(run({ types: new Set(["House"]), beds: 4, rent: 3500, inclCall: false })), "a");
  assert.equal(ids(run({ q: "area", types: new Set(["House"]) })), "b");
  assert.equal(ids(run({ furnished: true, utils: new Set(["Gas"]), q: "arlington" })), "d");
  assert.equal(ids(run({ furnished: true, rent: 1500, inclCall: false })), "d");
});

test("over-constrained filters return an empty list, not an error", () => {
  assert.deepEqual(run({ types: new Set(["Room"]), beds: 5 }), []);
});

// ---- sorting ----------------------------------------------------------------
test("default sort keeps the list order", () => {
  assert.equal(ids(run({ sort: "default" })), "abcdef");
});

test("price low-to-high puts listings with no rent last", () => {
  const r = run({ sort: "price-asc" });
  assert.deepEqual(r.map((x) => x.rent), [600, 1300, 2200, 3350, 3500, null]);
});

test("price high-to-low also puts listings with no rent last", () => {
  const r = run({ sort: "price-desc" });
  assert.deepEqual(r.map((x) => x.rent), [3500, 3350, 2200, 1300, 600, null]);
});

test("bedrooms sort is descending and stable for ties", () => {
  const r = run({ sort: "beds-desc" });
  assert.deepEqual(r.map((x) => x.id), ["b", "a", "c", "d", "e", "f"]);
});

test("location sort is alphabetical", () => {
  const r = run({ sort: "loc" }).map((x) => x.location);
  assert.deepEqual(r, [...r].sort((p, q) => p.localeCompare(q)));
});

test("sorting applies after filtering", () => {
  const r = run({ types: new Set(["House"]), sort: "price-desc" });
  assert.deepEqual(r.map((x) => x.id), ["a", "b"]);
});

test("searching does not mutate or reorder the source list", () => {
  const rows = fixture();
  const before = rows.map((x) => x.id).join("");
  S.search(rows, Object.assign(S.defaultState(), { sort: "price-desc", q: "a" }));
  assert.equal(rows.map((x) => x.id).join(""), before);
});

// ---- real data --------------------------------------------------------------
const data = pagePayload();

test("real listings: sane volume and the default view shows all of them", () => {
  assert.ok(data.listings.length >= 60);
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  assert.equal(S.search(rows, S.defaultState()).length, rows.length);
});

test("real listings: every listing is findable by its own location", () => {
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  for (const r of rows) {
    if (!r.location) continue;
    const hits = S.search(rows, Object.assign(S.defaultState(), { q: r.location }));
    assert.ok(hits.includes(r), `listing ${r.id} not found by "${r.location}"`);
  }
});

test("real listings: every listing with a phone is findable by it", () => {
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  for (const r of rows) {
    if (!r.phones.length) continue;
    const hits = S.search(rows, Object.assign(S.defaultState(), { q: r.phones[0] }));
    assert.ok(hits.includes(r), `listing ${r.id} not found by ${r.phones[0]}`);
  }
});

test("real listings: filters only ever narrow the results", () => {
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  const all = S.search(rows, S.defaultState()).length;
  for (const over of [{ beds: 3 }, { rent: 2000 }, { furnished: true }, { shortterm: true },
                      { types: new Set(["House"]) }, { utils: new Set(["Heat"]) }, { q: "jackson" }]) {
    const n = S.search(rows, Object.assign(S.defaultState(), over)).length;
    assert.ok(n <= all, JSON.stringify(over));
  }
});

// ---- the shipped page -------------------------------------------------------
const pagePath = path.join(ROOT, "docs", "index.html");
test("built page embeds the search core and the listing data", { skip: !fs.existsSync(pagePath) }, () => {
  const html = fs.readFileSync(pagePath, "utf8");
  assert.ok(html.includes("var LakewoodSearch"), "search core not inlined into the page");
  assert.ok(!html.includes("/*__SEARCH_CORE__*/"), "core placeholder left in page");
  assert.ok(!html.includes("/*__DATA__*/"), "data placeholder left in page");

  const m = html.match(/<script id="payload" type="application\/json">([\s\S]*?)<\/script>/);
  assert.ok(m, "payload script missing");
  const payload = JSON.parse(m[1]);
  assert.equal(payload.count, payload.listings.length);

  // Run the exact core code that ships in the page, against the shipped data.
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((x) => x[1]);
  const core = scripts.find((x) => x.includes("var LakewoodSearch"));
  assert.ok(core, "inline core script not found");
  const ctx = {};
  vm.runInNewContext(core + "\nthis.LS = LakewoodSearch;", ctx);
  const rows = ctx.LS.enrich(payload.listings);
  assert.equal(ctx.LS.search(rows, ctx.LS.defaultState()).length, payload.listings.length);
  const st = ctx.LS.defaultState();
  st.q = "toms river";
  assert.ok(ctx.LS.search(rows, st).length > 0);
});

// ---- distance ---------------------------------------------------------------
test("distanceMiles: known distances and symmetry", () => {
  assert.equal(S.distanceMiles(40.0979, -74.2179, 40.0979, -74.2179), 0);
  // Lakewood -> Toms River centre is roughly 12-13 miles
  const d = S.distanceMiles(40.0979, -74.2179, 39.9537, -74.1979);
  assert.ok(d > 9 && d < 12, String(d));
  assert.ok(Math.abs(d - S.distanceMiles(39.9537, -74.1979, 40.0979, -74.2179)) < 1e-9);
});

function geoFixture() {
  return S.enrich([
    L({ id: "near", lat: 40.0800, lng: -74.2100 }),
    L({ id: "far", lat: 40.1400, lng: -74.2200 }),
    L({ id: "mid", lat: 40.1000, lng: -74.2200 }),
    L({ id: "nowhere" }),                       // no coordinates
  ]);
}
const ORIGIN = { lat: 40.0790, lng: -74.2090 };
function runGeo(over) { return S.search(geoFixture(), Object.assign(S.defaultState(), { origin: ORIGIN }, over)); }

test("distance sort: nearest first, unplaced listings last", () => {
  assert.equal(ids(runGeo({ sort: "distance" })), "nearmidfarnowhere");
});

test("distance is attached to each listing when an origin is set", () => {
  const rows = runGeo({ sort: "distance" });
  assert.ok(rows[0]._dist < 0.3);
  assert.ok(rows[0]._dist < rows[1]._dist && rows[1]._dist < rows[2]._dist);
  assert.equal(rows[3]._dist, null);
});

test("no origin: distance sort falls back to list order", () => {
  const rows = S.search(geoFixture(), Object.assign(S.defaultState(), { sort: "distance" }));
  assert.equal(ids(rows), "nearfarmidnowhere");
  assert.ok(rows.every((r) => r._dist === null));
});

test("within-miles filter keeps only placed listings inside the radius", () => {
  assert.equal(ids(runGeo({ maxMiles: 2, sort: "distance" })), "nearmid");
  assert.equal(ids(runGeo({ maxMiles: 0.1 })), "near");
  assert.equal(ids(runGeo({ maxMiles: 50, sort: "distance" })), "nearmidfar"); // unplaced never pass a limit
});

test("maxMiles is ignored when there is no origin", () => {
  const rows = S.search(geoFixture(), Object.assign(S.defaultState(), { maxMiles: 1 }));
  assert.equal(rows.length, 4);
});

test("distance combines with other filters", () => {
  const rows = S.enrich([
    L({ id: "a", lat: 40.0800, lng: -74.2100, type: "House" }),
    L({ id: "b", lat: 40.0801, lng: -74.2101, type: "Room" }),
  ]);
  const st = Object.assign(S.defaultState(), { origin: ORIGIN, maxMiles: 2, sort: "distance", types: new Set(["Room"]) });
  assert.equal(ids(S.search(rows, st)), "b");
});

test("real listings: with Lakewood as origin, placed listings sort by distance", () => {
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  const placed = rows.filter((r) => typeof r.lat === "number");
  if (!placed.length) return; // places.json not built yet
  const out = S.search(rows, Object.assign(S.defaultState(), { origin: { lat: 40.0979, lng: -74.2179 }, sort: "distance" }));
  const ds = out.map((r) => r._dist).filter((d) => d !== null);
  assert.deepEqual(ds, [...ds].sort((a, b) => a - b));
  assert.equal(out.length, rows.length);
});


// ---- neighborhood suggestions (combined search box) ---------------------------------------
const PICK = [
  { name: "13th Street" }, { name: "14th Street" }, { name: "7th Street" }, { name: "E 7th Street" },
  { name: "Raintree" }, { name: "Ridge Avenue" }, { name: "Ridge Avenue & Negba Street" },
  { name: "Route 88" }, { name: "Sterling Forest" }, { name: "Sterling Place" },
  { name: "The Club at Jackson Twenty-One" }, { name: "Westgate" },
];
const names = (a) => a.map((p) => p.name);

test("suggestPlaces: nothing for blank input", () => {
  assert.deepEqual(S.suggestPlaces(PICK, ""), []);
  assert.deepEqual(S.suggestPlaces(PICK, "   "), []);
  assert.deepEqual(S.suggestPlaces(PICK, "&&"), []);
});

test("suggestPlaces: names that start with the text come first, shorter before longer", () => {
  assert.deepEqual(names(S.suggestPlaces(PICK, "ridge")), ["Ridge Avenue", "Ridge Avenue & Negba Street"]);
  assert.deepEqual(names(S.suggestPlaces(PICK, "ster")), ["Sterling Place", "Sterling Forest"]);
});

test("suggestPlaces: is case-insensitive and ignores punctuation", () => {
  assert.deepEqual(names(S.suggestPlaces(PICK, "RAIN")), ["Raintree"]);
  assert.deepEqual(names(S.suggestPlaces(PICK, "club, at jackson")), ["The Club at Jackson Twenty-One"]);
  assert.deepEqual(names(S.suggestPlaces(PICK, "route 88")), ["Route 88"]);
});

test("suggestPlaces: typed words can each start a different word of the name", () => {
  assert.deepEqual(names(S.suggestPlaces(PICK, "13 st")), ["13th Street"]);
  assert.deepEqual(names(S.suggestPlaces(PICK, "e 7")), ["E 7th Street"]);
  assert.deepEqual(names(S.suggestPlaces(PICK, "club jackson")), ["The Club at Jackson Twenty-One"]);
});

test("suggestPlaces: finds the text in the middle of a name, after prefix matches", () => {
  const r = names(S.suggestPlaces(PICK, "7th"));
  assert.deepEqual(r.slice(0, 1), ["7th Street"]);
  assert.ok(r.includes("E 7th Street"));
});

test("suggestPlaces: respects the limit and returns nothing when nothing matches", () => {
  const many = Array.from({ length: 30 }, (_, i) => ({ name: "Park " + i }));
  assert.equal(S.suggestPlaces(many, "park", 8).length, 8);
  assert.equal(S.suggestPlaces(many, "park").length, 8);
  assert.deepEqual(S.suggestPlaces(PICK, "zzzz"), []);
  assert.deepEqual(S.suggestPlaces(null, "a"), []);
});

test("activeFilterCount: counts switched-on filter groups, not search or distance", () => {
  const st = S.defaultState();
  assert.equal(S.activeFilterCount(st), 0);
  st.q = "raintree"; st.origin = { lat: 1, lng: 2 }; st.maxMiles = 3; st.sort = "price-asc";
  assert.equal(S.activeFilterCount(st), 0);
  st.types.add("House"); st.types.add("Room"); st.beds = 3; st.rent = 3000;
  st.inclCall = false; st.utils.add("Gas"); st.furnished = true; st.shortterm = true;
  assert.equal(S.activeFilterCount(st), 7);
});

test("real picker: typing a few letters of any suggested place finds that place first or near first", () => {
  const picker = data.picker || [];
  if (!picker.length) return;
  for (const p of picker.filter((x) => !x.list_only)) {           // list-only rows (55+) are not typed suggestions
    const typed = p.name.slice(0, Math.min(p.name.length, 6));
    assert.ok(names(S.suggestPlaces(picker, typed, 50)).includes(p.name), p.name);
  }
});

// ---- page wiring for the combined search box and the phone filter sheet --------------------
const templateHtml = fs.readFileSync(path.join(ROOT, "site", "template.html"), "utf8");

test("template: one search box that is an accessible combobox, with the Near chip inside it", () => {
  assert.match(templateHtml, /<input[^>]*id="q"[^>]*role="combobox"/);
  assert.match(templateHtml, /aria-controls="sugg"/);
  assert.match(templateHtml, /id="sugg"[^>]*role="listbox"/);
  assert.match(templateHtml, /id="nearChip"/);
  assert.match(templateHtml, /id="nearClear"[^>]*aria-label=/);
  assert.doesNotMatch(templateHtml, /id="nearInput"/);          // the second box is gone
  assert.doesNotMatch(templateHtml, /<datalist/);               // native datalist replaced by our list
});

test("template: removing the neighborhood needs no Enter (Backspace and the chip's x)", () => {
  assert.match(templateHtml, /e\.key === "Backspace" && !q\.value && S\.origin/);
  assert.match(templateHtml, /getElementById\("nearClear"\)\.onclick/);
  assert.doesNotMatch(templateHtml, /addEventListener\("change", placeFromInput\)/);
});

test("template: phone layout has a search bar outside the filters, and a filters sheet", () => {
  assert.ok(templateHtml.indexOf('id="searchbar"') < templateHtml.indexOf('class="wrap"'));
  const filtersAside = templateHtml.slice(templateHtml.indexOf('<aside class="filters"'), templateHtml.indexOf("</aside>"));
  assert.doesNotMatch(filtersAside, /id="q"/);                   // search is not hidden inside the filters
  assert.match(templateHtml, /id="filtersToggle"/);
  assert.match(templateHtml, /id="filtersDone"/);
  assert.match(templateHtml, /\[hidden\] \{ display: none !important; \}/);   // flex rules must not defeat `hidden`
});

test("template: the notice that this is an unofficial index of the Masa U'Matan list, with its links, stays on the page", () => {
  const fine = templateHtml.slice(templateHtml.indexOf('<div class="fineprint"'), templateHtml.indexOf("</main>"));
  assert.match(fine, /Masa U&rsquo;Matan/);
  assert.match(fine, /href="https:\/\/masaumatan\.com"/);
  assert.match(fine, /href="https:\/\/masaumatan\.com\/MasaRentals\.pdf"/);
  assert.match(fine, /not affiliated/);
  assert.doesNotMatch(templateHtml, /id="srcBtn"/);              // owner: no "Source" button in the top bar
});

test("real picker: typing 'clover' offers Clover first, and only one Clover", () => {
  const picker = data.picker || [];
  if (!picker.length) return;
  const r = names(S.suggestPlaces(picker, "clover"));
  assert.equal(r[0], "Clover");
  assert.equal(r.filter((n) => /clover/i.test(n)).length, 1);
});

test("real listings: picking Clover sorts a Clover listing first, before Arlington", () => {
  const picker = data.picker || [];
  const pin = picker.find((p) => p.name === "Clover");
  if (!pin) return;
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  const out = S.search(rows, Object.assign(S.defaultState(), { origin: { lat: pin.lat, lng: pin.lng, name: pin.name }, sort: "distance" }));
  const inClover = (r) => /clover/i.test(r.location) || (r.areas || []).includes("Clover");   // an address placed in Clover counts
  assert.ok(inClover(out[0]), out[0].location);   // at the same spot, a listing of the place comes before one that is not
  const iClover = out.findIndex((r) => /clover/i.test(r.location));
  const iArlington = out.findIndex((r) => /^arlington/i.test(r.location));
  assert.ok(iClover < iArlington);
});

test("template: declares UTF-8 so fractions like 3\u00bd render correctly (not 3\u00c2\u00bd)", () => {
  assert.match(templateHtml.slice(0, 200), /<meta charset="utf-8">/i);
});

test("suggestPlaces: a place is found by its other spellings too (Lutsk for Lutzk)", () => {
  const picker = [{ name: "Lutzk", aka: ["Lutsk"] }, { name: "Locust Street" }];
  assert.deepEqual(names(S.suggestPlaces(picker, "lutsk")), ["Lutzk"]);
  assert.deepEqual(names(S.suggestPlaces(picker, "lutz")), ["Lutzk"]);
  assert.deepEqual(names(S.suggestPlaces(picker, "locu")), ["Locust Street"]);
});

test("real picker: typing Lutsk or Lutzk offers Lutzk", () => {
  const picker = data.picker || [];
  if (!picker.length) return;
  assert.equal(names(S.suggestPlaces(picker, "lutsk"))[0], "Lutzk");
  assert.equal(names(S.suggestPlaces(picker, "lutzk"))[0], "Lutzk");
});

// ---- streets: any street in the area, sorted by distance to the street itself -----------------------------
// compact format: [name, townIndex, [path...]]; a path is the first point (offset from base) then steps, in 1e-4 degrees
function enc(points) {                       // points as [dlat, dlng] offsets from base
  const out = []; let pl = 0, pn = 0;
  for (const [la, ln] of points) { out.push(la - pl, ln - pn); pl = la; pn = ln; }
  return out;
}
const STREET_DATA = {
  base: [40.0, -74.4], unit: 0.0001, towns: ["Lakewood", "Jackson"],
  streets: [
    ["Ridge Avenue", 0, [enc([[990, 1915], [990, 2358]])]],        // long east-west street (lng -74.2085 .. -74.1642)
    ["Nowlan Place", 0, [enc([[960, 1987], [1010, 1987]])]],        // crosses it at lng -74.2013
    ["Ocean Avenue", 0, [enc([[907, 1900], [907, 2100]])]],         // Lakewood
    ["Ocean Avenue", 1, [enc([[1200, 400], [1200, 500]])]],         // a second, far-away one in Jackson
    ["Clover Street", 0, [enc([[887, 1997], [927, 1997]])]],
    ["Route 88", 0, [enc([[907, 1700], [907, 2300]])]],
  ],
};
const STREETS = S.decodeStreets(STREET_DATA);
const sn = (a) => a.map((s) => s.n + (s.t && a.filter((x) => x.n === s.n).length > 1 ? " (" + s.t + ")" : ""));

test("decodeStreets: turns the compact data into lines of [lat, lng]", () => {
  assert.equal(STREETS.length, 6);
  assert.deepEqual(STREETS[0].paths[0][0].map((v) => +v.toFixed(4)), [40.099, -74.2085]);
  assert.ok(STREETS[0].tokens.includes("ridge"));
  assert.deepEqual(S.decodeStreets(null), []);
});

test("pathMiles: distance to the street's line, not to its middle", () => {
  const ridge = STREETS[0].paths;
  const midLat = 40.099, midLng = -74.18635;
  assert.ok(S.pathMiles(midLat, midLng, ridge) < 0.001);                       // on the street
  assert.ok(S.pathMiles(midLat + 0.0145, midLng, ridge) > 0.95);                // 1 mile north of it
  // 1.1 miles past the east end: distance is to the end, not to the middle
  const past = S.pathMiles(40.099, -74.1642 + 0.0206, ridge);
  assert.ok(past > 1.0 && past < 1.2, past);
});

test("search: a street origin sorts listings by distance to the whole street", () => {
  const rows = S.enrich([
    L({ id: "east-end", lat: 40.0992, lng: -74.1650 }),       // beside the east end of Ridge Ave
    L({ id: "middle-off", lat: 40.1050, lng: -74.1863 }),     // 0.4 mi north of the middle
    L({ id: "far", lat: 40.0500, lng: -74.2000 }),
  ]);
  const street = STREETS[0];
  const st = Object.assign(S.defaultState(), { origin: { lat: street.lat, lng: street.lng, paths: street.paths }, sort: "distance" });
  assert.deepEqual(S.search(rows, st).map((r) => r.id), ["east-end", "middle-off", "far"]);
  // against the street's midpoint alone the east-end listing would have been 1.1 miles away, behind middle-off
  const pointOnly = Object.assign(S.defaultState(), { origin: { lat: street.lat, lng: street.lng }, sort: "distance" });
  assert.equal(S.search(S.enrich(rows.map((r) => Object.assign({}, r))), pointOnly)[0].id, "middle-off");
});

test("search: the within-miles limit also uses distance to the street", () => {
  const rows = S.enrich([L({ id: "a", lat: 40.0992, lng: -74.1650 }), L({ id: "b", lat: 40.0500, lng: -74.2000 })]);
  const street = STREETS[0];
  const st = Object.assign(S.defaultState(), { origin: { lat: street.lat, lng: street.lng, paths: street.paths }, maxMiles: 1 });
  assert.equal(ids(S.search(rows, st)), "a");
});

test("suggestStreets: matches typed street names, with abbreviations and a house number ignored", () => {
  assert.deepEqual(sn(S.suggestStreets(STREETS, "ridge")), ["Ridge Avenue"]);
  assert.deepEqual(sn(S.suggestStreets(STREETS, "ridge ave")), ["Ridge Avenue"]);
  assert.deepEqual(sn(S.suggestStreets(STREETS, "415 ridge ave")), ["Ridge Avenue"]);
  assert.deepEqual(sn(S.suggestStreets(STREETS, "now pl")), ["Nowlan Place"]);
  assert.deepEqual(sn(S.suggestStreets(STREETS, "RIDGE")), ["Ridge Avenue"]);
});

test("suggestStreets: one letter is too little; same name in two towns is two suggestions", () => {
  assert.deepEqual(S.suggestStreets(STREETS, "r"), []);
  assert.deepEqual(sn(S.suggestStreets(STREETS, "ocean")), ["Ocean Avenue (Lakewood)", "Ocean Avenue (Jackson)"]);
  assert.deepEqual(S.suggestStreets(STREETS, "zzzz"), []);
  assert.deepEqual(S.suggestStreets(null, "ridge"), []);
});

test("suggestCrossings: finds where two streets meet, in either order and with and / & / slash", () => {
  for (const text of ["clover & ocean", "ocean and clover", "Clover / Ocean Ave", "ocean@clover"]) {
    const c = S.suggestCrossings(STREETS, text);
    assert.equal(c.length, 1, text);
    assert.equal(c[0].name.includes("Clover Street") && c[0].name.includes("Ocean Avenue"), true, text);
    assert.ok(Math.abs(c[0].lat - 40.0907) < 0.0003 && Math.abs(c[0].lng - -74.2003) < 0.0003, text);
  }
});

test("suggestCrossings: streets that do not meet give no intersection, and the far-away namesake is not used", () => {
  assert.deepEqual(S.suggestCrossings(STREETS, "ridge & clover"), []);
  assert.deepEqual(S.suggestCrossings(STREETS, "clover"), []);                 // one street is not an intersection
  const c = S.suggestCrossings(STREETS, "nowlan & ridge");
  assert.equal(c.length, 1);
  assert.ok(Math.abs(c[0].lng - -74.2013) < 0.0003);
  assert.equal(S.suggestCrossings(STREETS, "ocean & route 88").length, 1);
});

test("suggestAll: an intersection comes first, places and streets are ranked by how well they match", () => {
  const picker = [{ name: "Clover", lat: 40.0907, lng: -74.2003 }, { name: "Raintree", lat: 40.0968, lng: -74.1646 }];
  const all = S.suggestAll(picker, STREETS, "clover");
  assert.deepEqual(all.map((i) => i.kind + ":" + i.name), ["place:Clover", "street:Clover Street"]);
  const x = S.suggestAll(picker, STREETS, "clover & ocean");
  assert.equal(x[0].kind, "cross");
  assert.ok(S.suggestAll(picker, STREETS, "rain").every((i) => i.kind === "place"));
  assert.equal(S.suggestAll(picker, STREETS, "ridge")[0].kind, "street");
  assert.deepEqual(S.suggestAll(picker, STREETS, ""), []);
});

test("suggestAll: a street result carries its lines so the page can sort by them", () => {
  const r = S.suggestAll([], STREETS, "ridge ave")[0];
  assert.equal(r.kind, "street");
  assert.ok(Array.isArray(r.paths) && r.paths[0].length >= 2);
  assert.equal(r.town, "Lakewood");
});

test("template: streets are wired into the search box, Enter and the empty state", () => {
  assert.match(templateHtml, /LakewoodSearch\.decodeStreets\(DATA\.streets\)/);
  assert.match(templateHtml, /LakewoodSearch\.suggestAll\(PICKER, STREETS/);
  assert.match(templateHtml, /paths: pl\.kind === "street" \? pl\.paths : null/);
  assert.match(templateHtml, /lastCount === 0/);                         // Enter takes the best suggestion when nothing matches
  assert.match(templateHtml, /No listing mentions/);
  assert.match(templateHtml, /OpenStreetMap contributors/);              // the street data's required credit
});

test("template: descriptions use a readable sans font at 15px or more (not the small condensed serif)", () => {
  const css = templateHtml.slice(templateHtml.indexOf(".card__desc {"), templateHtml.indexOf(".card__desc:empty"));
  assert.doesNotMatch(css, /Source Serif/);
  const px = +/font-size:\s*(\d+(?:\.\d+)?)px/.exec(css)[1];
  assert.ok(px >= 15, "font-size " + px);
  assert.match(css, /line-height:\s*1\.5/);
});

// ---- related words, other spellings and typos ----------------------------------------------------
function textRows() {
  return S.enrich([
    L({ id: "bochur", type: "Room", location: "Yeshiva Area", comments: "For Bochur. Separate entrance & bathroom." }),
    L({ id: "men", type: "House", location: "14th & Lexington", comments: "Furnished room in a house of single men. Use of W/D." }),
    L({ id: "guys", type: "Room", location: "Central", comments: "Priv. room, fully furn. house working guys. Shared kitchen." }),
    L({ id: "women", type: "Room", location: "Westgate", comments: "Furnished rooms for women/girls in shared house." }),
    L({ id: "apt", location: "Albert", comments: "Nice apartment with full basement. Available immediately." }),
    L({ id: "pool", type: "House", location: "Raintree", comments: "Colonial with finished bsmt, backyard and heated pool near the synagogue." }),
  ]);
}
const found = (text) => {
  const st = S.defaultState(); st.q = text;
  return S.search(textRows(), st).map((r) => r.id).sort();
};

test("boy, bachur, bocher and bochurim all find the same listings (single men / yeshiva boys)", () => {
  const want = ["bochur", "guys", "men"];
  for (const word of ["boy", "boys", "bochur", "bachur", "bocher", "bochurim", "bachurim", "guys", "yeshiva boy"]) {
    const got = found(word);
    if (word === "yeshiva boy") { assert.deepEqual(got, ["bochur"]); continue; }   // both words must match (AND)
    assert.deepEqual(got, want, word);
  }
});

test("related words are whole words: men does not match women, apartment or basement", () => {
  assert.deepEqual(found("men"), ["bochur", "guys", "men"]);
  assert.ok(!found("men").includes("women") && !found("men").includes("apt") && !found("men").includes("pool"));
});

test("girls and women find the women's listing, and not the men's", () => {
  assert.deepEqual(found("girl"), ["women"]);
  assert.deepEqual(found("women"), ["women"]);
});

test("other words for the same thing: synagogue/shul/minyan, bsmt/basement, apt/apartment", () => {
  assert.deepEqual(found("shul"), ["pool"]);
  assert.deepEqual(found("synagogue"), ["pool"]);
  assert.deepEqual(found("basement"), ["apt", "pool"]);
  assert.deepEqual(found("bsmt"), ["apt", "pool"]);
  assert.deepEqual(found("apartment"), ["apt"]);
  assert.deepEqual(found("apt"), ["apt"]);
});

test("small typos still find the word (needs 6+ letters, same first letter)", () => {
  assert.deepEqual(found("basment"), ["apt", "pool"]);
  assert.deepEqual(found("furnshed"), ["guys", "men", "women"]);
  assert.deepEqual(found("kitchn"), ["guys"]);
  assert.deepEqual(found("kit"), ["guys"]);                                        // 3 letters: a word beginning only
  assert.deepEqual(found("colonail"), ["pool"]);
  assert.deepEqual(found("Raintre"), ["pool"]);
  assert.deepEqual(found("bacher"), ["bochur", "guys", "men"]);                    // a spelling nobody listed
});

test("typos do not match unrelated words", () => {
  assert.deepEqual(found("bridge"), []);
  assert.deepEqual(found("zebra"), []);
  assert.deepEqual(found("poolside"), []);
});

test("exact searches still work exactly: phone numbers, locations and 3-letter words", () => {
  assert.deepEqual(found("732-555"), ["apt", "bochur", "guys", "men", "pool", "women"]);
  assert.deepEqual(found("westgate"), ["women"]);
  assert.deepEqual(found("wd"), ["men"]);
  assert.deepEqual(found("w/d"), ["men"]);
});

test("words combine with AND, each using related words and typos", () => {
  assert.deepEqual(found("boy furnished"), ["guys", "men"]);
  assert.deepEqual(found("bachur separate"), ["bochur"]);
  assert.deepEqual(found("synagogue pool"), ["pool"]);
});

test("editDistance counts one typo or one swap as 1 and gives up early", () => {
  assert.equal(S.editDistance("basement", "basment", 2), 1);
  assert.equal(S.editDistance("furnished", "furnished", 2), 0);
  assert.equal(S.editDistance("kitchen", "kitchne", 2), 1);              // swapped letters
  assert.equal(S.editDistance("pool", "garage", 2), 3);                  // "more than 2"
  assert.equal(S.editDistance("abc", "abcdefghi", 2), 3);
});

test("soundKey makes Hebrew spelling variants meet", () => {
  const key = S.soundKey;
  assert.equal(key("bochur"), key("bachur"));
  assert.equal(key("bochur"), key("bocher"));
  assert.equal(key("chosson"), key("chasan"));
  assert.equal(key("chasan"), key("chassan"));
  assert.notEqual(key("bochur"), key("raintree"));
});

test("relatedWords lists what a word also stands for", () => {
  const r = S.relatedWords("boy");
  assert.ok(r.includes("bochur") && r.includes("guys") && r.includes("men"));
  assert.ok(!r.includes("boys"));                                        // not the word itself (plural)
  assert.deepEqual(S.relatedWords("raintree"), []);
});

test("every concept has at least two words and no word is in two groups of different meaning by accident", () => {
  const seen = {};
  S.CONCEPTS.forEach((g, i) => {
    assert.ok(g.length >= 2, "group " + i);
    g.forEach((w) => { if (!/\s/.test(w)) { assert.ok(!(w in seen) || seen[w] === i, "'" + w + "' is in groups " + seen[w] + " and " + i); seen[w] = i; } });
  });
});

test("suggestions forgive typos: raintre, luzk, clifto", () => {
  const picker = [{ name: "Raintree" }, { name: "Lutzk" }, { name: "Clifton Avenue" }, { name: "Westgate" }];
  assert.equal(S.suggestPlaces(picker, "raintre")[0].name, "Raintree");
  assert.equal(S.suggestPlaces(picker, "luzk")[0].name, "Lutzk");
  assert.equal(S.suggestPlaces(picker, "clifto")[0].name, "Clifton Avenue");
  assert.deepEqual(S.suggestPlaces(picker, "qqqq"), []);
});

test("real listings: boy / bachur / bocher find the same listings, and 'For Bochur' is among them", () => {
  const rows = (w) => { const st = S.defaultState(); st.q = w; return S.search(S.enrich(data.listings.map((x) => Object.assign({}, x))), st).map((r) => r.id).sort(); };
  const a = rows("boy");
  assert.deepEqual(rows("bachur"), a);
  assert.deepEqual(rows("bocher"), a);
  assert.ok(a.length >= 1);
  if (data.listings.some((x) => /bochur/i.test(x.comments))) {
    assert.ok(data.listings.filter((x) => /bochur/i.test(x.comments)).every((x) => a.includes(x.id)));
  }
});

test("template: the page tells the visitor which related words are also being matched", () => {
  assert.match(templateHtml, /id="related"/);
  assert.match(templateHtml, /Also matching related words/);
  assert.match(templateHtml, /LakewoodSearch\.relatedWords\(w\)/);
});

test("a street flagged as a duplicate of a neighborhood is not suggested, but still makes intersections", () => {
  const data = JSON.parse(JSON.stringify(STREET_DATA));
  data.streets[4].push(1);                                         // Clover Street duplicates the Clover neighborhood
  const streets = S.decodeStreets(data);
  assert.deepEqual(S.suggestStreets(streets, "clover"), []);
  assert.equal(S.suggestStreets(streets, "clover", 8, true).length, 1);
  assert.equal(S.suggestCrossings(streets, "clover & ocean").length, 1);
  assert.ok(S.suggestAll([], streets, "clover").every((i) => i.kind !== "street"));
  assert.equal(S.suggestAll([], streets, "clover & ocean")[0].kind, "cross");
});

test("suggestions never treat a number as a typo: 13th is not 10th", () => {
  const picker = [{ name: "10th Street" }, { name: "13th Street" }, { name: "14th Street" }];
  assert.deepEqual(names(S.suggestPlaces(picker, "13th")), ["13th Street"]);
  assert.deepEqual(names(S.suggestPlaces(picker, "12th")), []);
});

test("template: a street origin says distances are to the street, a neighborhood says to its middle", () => {
  assert.match(templateHtml, /closest point on the street/);
  assert.match(templateHtml, /middle of each neighborhood/);
});

test("real streets: ocean avenue, cedar bridge and an intersection are found in the shipped street data", () => {
  const fs2 = require("node:fs");
  const file = path.join(ROOT, "streets.json");
  if (!fs2.existsSync(file)) return;
  const streets = S.decodeStreets(JSON.parse(fs2.readFileSync(file, "utf8")));
  assert.ok(S.suggestStreets(streets, "cedar bridge").some((s) => s.n === "Cedar Bridge Avenue"));
  assert.ok(S.suggestStreets(streets, "ocean ave", 20).some((s) => s.n === "Ocean Avenue"));
  assert.ok(S.suggestStreets(streets, "415 laurel ave").some((s) => s.n === "Laurel Avenue" && s.t === "Lakewood"));
  const x = S.suggestCrossings(streets, "clover & ocean")[0];
  assert.ok(x && Math.abs(x.lat - 40.0907) < 0.002 && Math.abs(x.lng - -74.2003) < 0.002, JSON.stringify(x));
  const r = S.suggestCrossings(streets, "ridge and nowlan")[0];
  assert.ok(r && Math.abs(r.lat - 40.0991) < 0.002 && Math.abs(r.lng - -74.2015) < 0.002, JSON.stringify(r));
});

test("streets: among equally good matches Lakewood's own come first, wherever the other towns' streets are", () => {
  const data = {
    base: [40.0, -74.4], unit: 0.0001, towns: ["Lakewood", "Jackson", "Brick"],
    streets: [
      ["Birch Court", 2, [enc([[500, 2500], [520, 2500]])]],          // Brick: shorter name, nearest-listed alphabetically
      ["Birch Street", 1, [enc([[1000, 500], [1010, 500]])]],         // Jackson
      ["Birchwood Drive", 0, [enc([[950, 2000], [960, 2000]])]],      // Lakewood
    ],
  };
  const streets = S.decodeStreets(data);
  assert.deepEqual(S.suggestStreets(streets, "birch").map((s) => s.n + "|" + s.t),
    ["Birchwood Drive|Lakewood", "Birch Court|Brick", "Birch Street|Jackson"]);
  assert.equal(S.suggestStreets(streets, "birch")[0].t, "Lakewood");
  assert.equal(S.suggestAll([], streets, "birch")[0].town, "Lakewood");
});

test("suggestAll: a neighborhood carries its town, just like a street", () => {
  const picker = [{ name: "Harfield", town: "Jackson", lat: 40.14, lng: -74.27 }, { name: "Raintree", town: "Lakewood", lat: 40.09, lng: -74.16 },
                  { name: "Jackson", lat: 40.1, lng: -74.35 }];
  const h = S.suggestAll(picker, [], "harf")[0];
  assert.equal(h.kind, "place");
  assert.equal(h.town, "Jackson");
  assert.equal(S.suggestAll(picker, [], "rain")[0].town, "Lakewood");
  assert.equal(S.suggestAll(picker, [], "jackson")[0].town, undefined);      // a town is not in itself
});

test("template: the suggestion list shows the town for neighborhoods, streets and intersections", () => {
  assert.match(templateHtml, /var hint = pl\.kind === "cross"/);
  assert.match(templateHtml, /\(pl\.town \|\| ""\)/);
});

test("real picker: every neighborhood suggestion has a town, except the towns themselves", () => {
  const picker = data.picker || [];
  if (!picker.length) return;
  const TOWNS = ["Lakewood", "Jackson", "Howell", "Toms River", "Manchester", "Brick"];
  for (const p of picker) {
    if (TOWNS.includes(p.name)) assert.equal(p.town, undefined, p.name);
    else assert.ok(TOWNS.includes(p.town), p.name + " has no town");
  }
  const by = Object.fromEntries(picker.map((p) => [p.name, p.town]));
  assert.equal(by["Harfield"], "Jackson");
  assert.equal(by["Harmony Farms"], "Jackson");
  assert.equal(by["Harmony Hills"], "Jackson");
});

// ---- 55+ communities: a search term, a one-tap filter, and a suggestion ------------------------------------
function ageRows() {
  return S.enrich([
    L({ id: "text", location: "Westgate", comments: "55+community. Fully renovated. Pesach kitchen." }),
    L({ id: "place", location: "Fairways", comments: "Beautifully renovated, near several Shuls, full basement." }),
    L({ id: "enc", location: "22 Enclave Blvd.", comments: "One year lease. Available immediately." }),
    L({ id: "word", location: "55+Community", comments: "Available immediately." }),
    L({ id: "senior", location: "Albert", comments: "Quiet senior community, 55 plus." }),
    L({ id: "phone", location: "Raintree", comments: "Nice house.", phones: ["732-555-0101"] }),
    L({ id: "plain", location: "Pawnee", comments: "Brand new apartment." }),
  ]);
}
const age = (text) => { const st = S.defaultState(); st.q = text; return S.search(ageRows(), st).map((r) => r.id).sort(); };

test("normalizeQuery: every way of saying 55+ becomes 55+", () => {
  for (const q of ["55+", "55 plus", "55plus", "55 Plus", "over 55", "Over 55", "55 and over", "55 and older", "fifty five plus", "fifty-five+",
                   "senior community", "active adult", "adult living", "age restricted community", "retirement community"]) {
    assert.equal(S.normalizeQuery(q), "55+", q);
  }
  assert.equal(S.normalizeQuery("Raintree 55 plus furnished"), "raintree 55+ furnished");
  assert.equal(S.normalizeQuery("2 bedroom"), "2 bedroom");
  assert.equal(S.normalizeQuery("555"), "555");
});

test("55+ is searchable: 55+, 55 plus, over 55, senior all find the 55+ listings", () => {
  const want = ["enc", "place", "senior", "text", "word"];
  for (const q of ["55+", "55 plus", "55plus", "over 55", "55 and over", "senior", "seniors", "senior community", "active adult"]) {
    assert.deepEqual(age(q), want, q);
  }
});

test("a listing is a 55+ one if it says so OR is in the Fairways or the Enclave", () => {
  assert.ok(age("55+").includes("place"));          // Fairways: no mention of 55+ in its text
  assert.ok(age("55+").includes("enc"));            // 22 Enclave Blvd.: nor here
});

test("searching the neighborhood name finds only that neighborhood, not every 55+ listing", () => {
  assert.deepEqual(age("fairways"), ["place"]);
  assert.deepEqual(age("enclave"), ["enc"]);
});

test("a bare number is a whole word: 55 does not match the phone number 732-555-0101", () => {
  assert.ok(!age("55").includes("phone"));
  assert.deepEqual(age("55"), ["senior", "text", "word"]);       // the word "55" in "55+community", "55+Community", "55 plus"
  assert.deepEqual(age("732"), ["enc", "phone", "place", "plain", "senior", "text", "word"].sort());
  assert.equal(age("732-555").length, 7);                        // phone searches still match as text (every fixture row has it)
  assert.equal(age("732-555-0101").length, 7);
});

test("the 55+ filter keeps only those listings, and combines with the other filters", () => {
  const st = S.defaultState(); st.age55 = true;
  assert.deepEqual(S.search(ageRows(), st).map((r) => r.id).sort(), ["enc", "place", "senior", "text", "word"]);
  st.q = "renovated";
  assert.deepEqual(S.search(ageRows(), st).map((r) => r.id).sort(), ["place", "text"]);
  assert.equal(S.defaultState().age55, false);
});

test("the visible 55+ chip is not counted in the Filters badge", () => {
  const st = S.defaultState(); st.age55 = true;
  assert.equal(S.activeFilterCount(st), 0);
});

test("suggestions offer 55+ communities as a topic first, and only for 55+ words", () => {
  for (const q of ["55", "55+", "55 plus", "over 55", "senior", "seniors", "active adult", "retire"]) {
    const first = S.suggestAll([], [], q)[0];
    assert.ok(first && first.kind === "topic" && first.topic === "age55", q);
  }
  for (const q of ["rain", "fairways", "ocean", "13th", "furnished"]) {
    assert.ok(S.suggestAll([{ name: "Fairways", lat: 1, lng: 2 }, { name: "Raintree", lat: 1, lng: 2 }], [], q).every((i) => i.kind !== "topic"), q);
  }
});

test("template: a 55+ chip in the search bar, wired to the filter and to the topic suggestion", () => {
  assert.match(templateHtml, /id="age55Btn"/);
  assert.match(templateHtml, /function setAge55\(on\)/);
  assert.match(templateHtml, /pl\.kind === "topic"\) \{ setAge55\(true\)/);
  assert.match(templateHtml, /only 55\+ listings/);
  assert.match(templateHtml, /LakewoodSearch\.normalizeQuery\(S\.q\)/);
});

test("real listings: the 55+ filter finds the Fairways, the Enclave and the 55+ listing", () => {
  const rows = S.enrich(data.listings.map((x) => Object.assign({}, x)));
  const st = S.defaultState(); st.age55 = true;
  const got = S.search(rows, st);
  assert.ok(got.length >= 1);
  assert.ok(got.every((r) => /fairways|enclave|55/i.test(r.location + " " + r.comments)));
  const typed = S.defaultState(); typed.q = "55 plus";
  assert.deepEqual(S.search(rows, typed).map((r) => r._i).sort(), got.map((r) => r._i).sort());
});

// ---- short typos and sounds-like: "jak" for Jackson --------------------------------------------------------------
test("closeWord: a typo of the start of a word, or something that sounds like it", () => {
  assert.ok(S.closeWord("jak", "jackson"));        // one letter off the start, and j-k starts j-k-s-n
  assert.ok(S.closeWord("jaks", "jackson"));
  assert.ok(S.closeWord("jaksn", "jackson"));
  assert.ok(S.closeWord("raintre", "raintree"));
  assert.ok(S.closeWord("luzk", "lutzk"));
  assert.ok(S.closeWord("brookwod", "brookwood"));
  assert.ok(!S.closeWord("jak", "raintree"));
  assert.ok(!S.closeWord("jak", "howell"));
  assert.ok(!S.closeWord("bak", "jackson"));        // the first letter must be the same
});

test("suggestions: jak and its misspellings offer Jackson first", () => {
  const picker = [{ name: "Raintree", town: "Lakewood" }, { name: "Jackson" }, { name: "Jackson 21", town: "Jackson" }, { name: "Howell" }];
  for (const q of ["jak", "jaks", "jacks", "jaksn", "jackso", "Jak", "JAK"]) {
    assert.equal(S.suggestPlaces(picker, q)[0].name, "Jackson", q);
  }
  assert.deepEqual(S.suggestPlaces(picker, "jak").map((p) => p.name), ["Jackson", "Jackson 21"]);
  assert.deepEqual(S.suggestPlaces(picker, "qxz"), []);
});

test("suggestions with streets: jak finds Jackson's streets too, after the town", () => {
  const data = { base: [40.0, -74.4], unit: 0.0001, towns: ["Lakewood", "Jackson"],
                 streets: [["Jackson Mills Road", 1, [enc([[1000, 500], [1010, 500]])]], ["Raintree Lane", 0, [enc([[900, 2000], [910, 2000]])]]] };
  const all = S.suggestAll([{ name: "Jackson" }], S.decodeStreets(data), "jak");
  assert.deepEqual(all.map((i) => i.name), ["Jackson", "Jackson Mills Road"]);
});

test("listing text: a short misspelling matches only when nothing matches exactly (jak -> Jacksn, Jackson)", () => {
  const rows = () => S.enrich([
    L({ id: "jacksn", location: "Hyson Area, Jacksn", comments: "Nice house." }),
    L({ id: "jackson", location: "Jackson", comments: "Quiet street." }),
    L({ id: "rain", location: "Raintree", comments: "Beautiful ranch." }),
    L({ id: "pool", location: "Westgate", comments: "Heated pool and yard." }),
    L({ id: "pole", location: "Albert", comments: "Pole barn nearby." }),
  ]);
  const f = (t) => { const st = S.defaultState(); st.q = t; return S.search(rows(), st).map((r) => r.id).sort(); };
  assert.deepEqual(f("jak"), ["jacksn", "jackson"]);
  assert.deepEqual(f("jaks"), ["jacksn", "jackson"]);
  assert.deepEqual(f("pool"), ["pool"]);                      // matches exactly, so "pole" is not dragged in
  assert.deepEqual(f("zqx"), []);
  assert.deepEqual(f("jak ranch"), []);                       // both words must match
  assert.deepEqual(f("jak house"), ["jacksn"]);
});

test("the empty state offers the suggestion when the text matches no listing (jak)", () => {
  assert.match(templateHtml, /No listing mentions/);
  const st = S.defaultState(); st.q = "xj";
  assert.deepEqual(S.search(S.enrich([L({ id: "a" })]), st), []);
});

test("typo suggestions appear only when nothing matches properly (ster -> Sterling, not every Street)", () => {
  const picker = [{ name: "Sterling Forest" }, { name: "Sterling Place" }, { name: "7th Street" }, { name: "Ridge Avenue & Negba Street" }];
  assert.deepEqual(names(S.suggestPlaces(picker, "ster")), ["Sterling Place", "Sterling Forest"]);
  assert.deepEqual(S.suggestAll(picker, [], "ster").map((i) => i.name), ["Sterling Place", "Sterling Forest"]);
  // but with no proper match at all, the near-misses are offered
  assert.ok(names(S.suggestPlaces(picker, "stirling")).includes("Sterling Place"));
});

// ---- shuls ("near this shul") -----------------------------------------------
const SHULS = [
  { name: "Bais Medrash Heichal Hatorah", lat: 40.09, lng: -74.21, town: "Lakewood", address: "10 Main St", aka: [] },
  { name: "Congregation Heichal Menachem", lat: 40.17, lng: -74.2, town: "Howell", address: "", aka: [] },
  { name: "Chabad of Jackson, NJ", lat: 40.1, lng: -74.22, town: "Lakewood", address: "645 Cross St", aka: [] },
  { name: "Spruce Street Shul", lat: 40.08, lng: -74.2, town: "Lakewood", address: "", aka: [] },
  { name: "Beis Medrash Ohel Torah", lat: 40.07, lng: -74.2, town: "Lakewood", address: "958 E County Line Rd", aka: [] },
];

test("shuls: found by name, in any spelling of beis/bais/beit medrash/midrash", () => {
  assert.equal(S.suggestShuls(SHULS, "heichal")[0].name, "Bais Medrash Heichal Hatorah");   // Lakewood before Howell
  assert.equal(S.suggestShuls(SHULS, "heichal").length, 2);
  assert.equal(S.suggestShuls(SHULS, "beit midrash ohel")[0].name, "Beis Medrash Ohel Torah");
  assert.equal(S.suggestShuls(SHULS, "bais medrash ohel torah")[0].name, "Beis Medrash Ohel Torah");
});

test("shuls: generic words are ignored when something specific is typed", () => {
  assert.equal(S.suggestShuls(SHULS, "chabad shul")[0].name, "Chabad of Jackson, NJ");
  assert.equal(S.suggestShuls(SHULS, "spruce")[0].name, "Spruce Street Shul");
  assert.equal(S.suggestShuls(SHULS, "x").length, 0);
});

test("shuls: appear in the combined suggestions with their town, ahead of weaker matches", () => {
  const picker = [{ name: "Heights", town: "Lakewood", lat: 40.09, lng: -74.2 }];
  const all = S.suggestAll(picker, [], "spruce", 8, SHULS);
  assert.equal(all[0].kind, "shul");
  assert.equal(all[0].town, "Lakewood");
  assert.equal(S.suggestAll(picker, [], "heights", 8, SHULS)[0].kind, "place");
});

test("shuls: the real list has Lakewood shuls with coordinates near Lakewood", () => {
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, "shuls.json"), "utf8")).shuls;
  assert.ok(data.length > 150);
  assert.ok(data.every((s) => Math.abs(s.lat - 40.1) < 0.2 && Math.abs(s.lng + 74.2) < 0.25));
  assert.ok(S.suggestShuls(data.map((s) => Object.assign({ aka: [] }, s)), "heichal hachassidus").length >= 1);
});

test("shuls: a neighborhood that is also a shul shows once, and BMG finds every BMG building", () => {
  const picker = [{ name: "Kol Shimshon", town: "Lakewood", lat: 40.1, lng: -74.2, shul: true },
                  { name: "BMG (Main Building, 6th St)", town: "Lakewood", lat: 40.095, lng: -74.222, shul: true, aka: ["BMG"] }];
  const shuls = [{ name: "BMG - Bais Aharon (10th St)", lat: 40.099, lng: -74.217, town: "Lakewood", address: "350 10th St", aka: ["BMG"] },
                 { name: "Kol Aryeh", lat: 40.105, lng: -74.242, town: "Lakewood", address: "521 Hope Chapel Rd", aka: [] }];
  const kol = S.suggestAll(picker, [], "kol", 8, shuls);
  assert.deepEqual(kol.map((i) => i.name + ":" + i.kind), ["Kol Shimshon:place", "Kol Aryeh:shul"]);
  assert.equal(kol[0].shul, true);
  const bmg = S.suggestAll(picker, [], "bmg", 8, shuls).map((i) => i.name);
  assert.ok(bmg.includes("BMG - Bais Aharon (10th St)") && bmg.includes("BMG (Main Building, 6th St)"));
});

test("suggestions: another spelling of a place ('BMG', 'Yeshiva') finds it even when its own name does not match", () => {
  const picker = [{ name: "Bais Shalom", town: "Lakewood", lat: 40.099, lng: -74.217, aka: ["BMG"], shul: true }];
  assert.equal(S.suggestAll(picker, [], "bmg", 8, [])[0].name, "Bais Shalom");
});

test("shuls: a whole-word match comes before a longer word that merely starts the same", () => {
  const shuls = [{ name: "Kollel Ner Avrohom", lat: 40.1, lng: -74.2, town: "Lakewood", address: "", aka: [] },
                 { name: "Kol Aryeh", lat: 40.1, lng: -74.2, town: "Lakewood", address: "", aka: [] }];
  assert.equal(S.suggestShuls(shuls, "kol")[0].name, "Kol Aryeh");
});

// ---- the page map -------------------------------------------------------------
test("map: pins are grouped by spot, with short prices and an honest circle size", () => {
  const a = L({ id: "a", lat: 40.1, lng: -74.2, rent: 1800 }), b = L({ id: "b", lat: 40.1, lng: -74.2, rent: 950 });
  const c = L({ id: "c", lat: 40.11, lng: -74.21, rent: null, rent_display: "Call to discuss" }), d = L({ id: "d", rent: 700 });
  const g = S.groupByPoint([a, b, c, d]);                  // d has no point
  assert.equal(g.length, 2);
  assert.deepEqual(g[0].rows.map((x) => x.id), ["a", "b"]);
  assert.equal(S.rentLabel(a), "$1.8k");
  assert.equal(S.rentLabel(b), "$950");
  assert.equal(S.rentLabel(c), "Call");
  assert.equal(S.rentLabel(L({ rent: null, rent_display: "$450/week" })), "$450/wk");
  assert.equal(S.uncertaintyMiles(L({ geo: "place" })), 0.15);
  assert.equal(S.uncertaintyMiles(L({ geo: "town" })), 1);
  assert.ok(S.uncertaintyMiles(L({ geo: "place", geo_spread: 0.8 })) >= 0.5);   // two places averaged: somewhere between
});

test("search: typing just 'shul' tells the visitor to type a shul's name", () => {
  const shuls = [{ name: "Spruce Street Shul", lat: 40.08, lng: -74.2, town: "Lakewood", address: "", aka: [] }];
  for (const w of ["shul", "synagogue", "minyan", "bais medrash"]) {
    const all = S.suggestAll([], [], w, 8, shuls);
    assert.equal(all[0].kind, "hint", w);
  }
  assert.notEqual(S.suggestAll([], [], "spruce", 8, shuls)[0].kind, "hint");
});

test("hasPrice: a listing shows a price when it has a monthly or weekly rent", () => {
  assert.equal(S.hasPrice(L({ rent: 1800 })), true);
  assert.equal(S.hasPrice(L({ rent: null, rent_display: "$450/week" })), true);
  assert.equal(S.hasPrice(L({ rent: null, rent_display: "Call to discuss" })), false);
});

test("map: every shul in shuls.json is a marker on the page, with a town", () => {
  const pins = data.shulpins || [];
  const file = JSON.parse(fs.readFileSync(path.join(ROOT, "shuls.json"), "utf8")).shuls.filter((s) => !s.hide);
  assert.equal(pins.length, file.length);
  assert.ok(pins.length > 200);
  assert.ok(pins.every((p) => typeof p[1] === "number" && typeof p[2] === "number" && p[3]));
});

// ---- typing a place is a location search --------------------------------------

test("placeIntent: a place, shul or street typed in the box means 'near it'; ordinary words stay keywords", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const of = (q) => { const r = S.placeIntent(q, data.picker, streets, shuls, data.preferred); return r ? r.item.name + (r.rest ? " +" + r.rest : "") : null; };
  assert.equal(of("raintree"), "Raintree");
  assert.equal(of("Raintree "), "Raintree");
  assert.equal(of("bmg"), "BMG");                               // owner: BMG alone = the campus between 6th and 7th
  assert.equal(of("kol aryeh"), "Kol Aryeh");
  assert.equal(of("beis aharon"), "Beis Aharon");
  assert.equal(of("spruce st"), "Spruce Street");
  assert.equal(of("raintree pool"), "Raintree +pool");          // a place plus a keyword
  assert.equal(of("furnished raintree"), "Raintree +furnished");
  assert.match(of("clover & ocean"), /Clover/);                 // an intersection
  assert.equal(of("yeshiva"), "BMG");                           // owner: "yeshiva" means BMG
  assert.equal(of("forest"), "Forest Avenue");                  // owner: the street people mean by "forest"
  assert.equal(of("birch"), "Birch Street");                    // ... and by "birch" (Lakewood, at Williams)
  assert.equal(of("forest ave"), "Forest Avenue");              // more words single the street out
  // typos of a place are that place (owner, 2026-11-24): "foreset" is Forest Avenue, not Sterling Forest
  for (const w of ["foreset", "forset", "forrest"]) assert.equal(of(w), "Forest Avenue", w);
  assert.equal(of("spruse street"), "Spruce Street");
  assert.equal(of("kol aryh"), "Kol Aryeh");
  assert.equal(of("raintrea"), "Raintree");
  assert.equal(of("jak"), "Jackson");
  assert.equal(of("sterling forest"), "Sterling Forest");       // if you meant Sterling Forest you type Sterling first
  for (const w of ["pool", "boy", "basement", "furnishd", "basment", "poool", "55+", "shul", "ra", "zzzzqq", "qwertyu"]) assert.equal(of(w), null, w);   // keywords (and typos of keywords)
});

test("suggestions: 'yeshiva' gives exactly the 'bmg' list, the 6th-7th St campus first; forest/birch put the usual street first", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const names = (q) => S.suggestAll(data.picker, streets, q, 8, shuls, data.preferred).map((i) => i.name);
  assert.deepEqual(names("yeshiva"), names("bmg"));
  assert.equal(names("yeshiva")[0], "BMG");
  for (const n of ["Beis Shalom", "Beis Aharon", "Forest Beis Medrash", "Princeton Beis Medrash"]) assert.ok(names("yeshiva").includes(n), n);
  const forest = S.suggestAll(data.picker, streets, "forest", 8, shuls, data.preferred);
  assert.equal(forest[0].name, "Forest Avenue");
  assert.equal(S.suggestAll(data.picker, streets, "foreset", 8, shuls, data.preferred)[0].name, "Forest Avenue");   // a typo, still first
  assert.equal(forest[0].town, "Lakewood");
  assert.ok(forest.slice(1).every((i) => i.name !== "Forest Avenue" || i.town !== "Lakewood"));   // not listed twice
  const birch = S.suggestAll(data.picker, streets, "birch", 8, shuls, data.preferred);
  assert.equal(birch[0].name + " " + birch[0].town, "Birch Street Lakewood");
});



test("searchAll: a keyword puts the matching listings first and keeps every other listing below them", () => {
  const rows = S.enrich([
    L({ id: "a", location: "Raintree", comments: "Has a pool and a big yard." }),
    L({ id: "b", location: "Albert", comments: "Quiet street." }),
    L({ id: "c", location: "Pawnee", comments: "Pool access in the community.", rent: 1500 }),
    L({ id: "d", location: "Marc Drive", type: "Room", comments: "Furnished room." }),
  ]);
  const st = S.defaultState();
  st.q = "pool";
  let r = S.searchAll(rows, st);
  assert.deepEqual(r.matches.map((x) => x.id), ["a", "c"]);
  assert.deepEqual(r.others.map((x) => x.id), ["b", "d"]);
  assert.ok(r.matches.every((x) => x._kw === true) && r.others.every((x) => x._kw === false));
  // the other filters are still strict: a type filter removes listings from both groups
  st.types = new Set(["Apartment"]);
  r = S.searchAll(rows, st);
  assert.deepEqual(r.others.map((x) => x.id), ["b"]);
  // each group follows the sort
  st.types = new Set(); st.sort = "price-asc";
  r = S.searchAll(rows, st);
  assert.deepEqual(r.matches.map((x) => x.id), ["c", "a"]);
  // no words: everything is a match
  st.q = "";
  r = S.searchAll(rows, st);
  assert.equal(r.matches.length, 4);
  assert.equal(r.others.length, 0);
  // words nobody uses: no matches, but the whole list is still there
  st.q = "zzzzz";
  r = S.searchAll(rows, st);
  assert.equal(r.matches.length, 0);
  assert.equal(r.others.length, 4);
});

test("uncertaintyMiles: a town-only listing is as wide as the Jewish area of that town (0.5 to 1.5 mi)", () => {
  assert.equal(S.uncertaintyMiles(L({ geo: "town", geo_area_miles: 0.4 })), 0.5);
  assert.equal(S.uncertaintyMiles(L({ geo: "town", geo_area_miles: 2.5 })), 1.5);
  assert.equal(S.uncertaintyMiles(L({ geo: "town", geo_area_miles: 1.1 })), 1.1);
  assert.equal(S.uncertaintyMiles(L({ geo: "town" })), 1);
});

test("suggestions: a typed word does not match the middle of another word ('pool' is not Liverpool)", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const names = S.suggestAll(data.picker, streets, "pool", 8, [], data.preferred).map((i) => i.name);
  assert.ok(!names.some((n) => /liverpool/i.test(n)), names.join(", "));
  assert.ok(S.relatedWords("pool").includes("swimming pool"));      // the page offers these as keyword suggestions
});

test("browse list: a neighborhood written with its town ('New Prospect Jackson') is still listed", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const of = (n) => { const it = S.placeForName(n, data.picker, streets, shuls, data.preferred); return it && it.name; };
  assert.equal(of("New Prospect Jackson"), "New Prospect");
  assert.equal(of("Brookwood 4 Jackson"), "Brookwood 4");
  assert.equal(of("Harmony Hills Jackson"), "Harmony Hills");
  assert.equal(of("Mackenzie Area Toms River"), "Mackenzie");
  assert.equal(of("Jackson"), "Jackson");                       // a town on its own is not stripped away
  assert.equal(of("55+Community"), "55+ Communities (Fairways / Enclave)");   // the one 55+ row (owner)
  assert.equal(of("Prime Jackson"), null);                      // owner: never its own row (listed under Jackson)
});

test("browse list: owner's neighborhoods (Chestnut, Locust, Chateau, Jackson 21, Oak Meadows, The Vineyards)", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const of = (n) => { const it = S.placeForName(n, data.picker, streets, shuls, data.preferred); return it && it.kind + ":" + it.name; };
  for (const [name, want] of [["Chestnut", "Chestnut"], ["Off Chestnut", "Chestnut"], ["Locust", "Locust"], ["Off Locust St.", "Locust"],
                              ["Near Chateau", "Chateau Park"], ["Club at Jackson 21", "Jackson 21"], ["Club 21 Jackson", "Jackson 21"],
                              ["Oak Meadows", "Oak Meadows"], ["The Vineyards", "The Vineyards"], ["Chestnut Acres", "Chestnut Acres"],
                              ["Locust Grove", "Locust Grove"]]) assert.equal(of(name), "place:" + want, name);
});

// ---- one grouping for the neighbourhood lists, and shared areas ----------------
test("lists: a listing in a shared area counts under each of its neighbourhoods, once", () => {
  const resolve = (n) => ({ "albert run": { kind: "place", name: "Albert Run" }, sims: { kind: "place", name: "Sims" },
    albert: { kind: "place", name: "Albert" }, "off locust st.": { kind: "place", name: "Locust" }, locust: { kind: "place", name: "Locust" },
    "marc drive": { kind: "street", name: "Marc Drive" } })[n.toLowerCase()] || null;
  const rows = [L({ id: "a", location: "Albert Run / Sims", areas: ["Albert Run", "Sims", "Albert"] }), L({ id: "b", location: "Albert Area" }),
                L({ id: "c", location: "Off Locust St." }), L({ id: "d", location: "Marc Drive" })];
  const g = S.placeGroups(rows, ["Locust", "55+Community"], resolve);
  assert.deepEqual(g.nb.map((x) => x.name + " " + x.n), ["Albert 2", "Albert Run 1", "Locust 1", "Sims 1"]);
  assert.deepEqual(g.st.map((x) => x.name + " " + x.n), ["Marc Drive 1"]);
});

test("search: a listing in a shared area is 'right here' for each of its neighbourhoods", () => {
  const here = L({ id: "a", lat: 40.069, lng: -74.197, areas: ["Albert Run", "Sims", "Albert"] });
  const near = L({ id: "b", lat: 40.064, lng: -74.199 });
  const st = S.defaultState();
  st.origin = { lat: 40.064, lng: -74.199, name: "Albert" }; st.sort = "distance";
  S.search([near, here], st);
  assert.equal(here._dist, 0);
  st.origin = { lat: 40.064, lng: -74.199, name: "Raintree" };
  S.search([near, here], st);
  assert.ok(here._dist > 0.2);
});

test("real data: Sims, Albert Run and Albert all include the Radiant Hill listing, if it is still listed", () => {
  const data = pagePayload();
  const x = data.listings.find((l) => /^albert run|^sims/i.test(l.location));
  if (!x) return;                                                 // weekly list moved on
  assert.deepEqual(x.areas.slice().sort(), ["Albert", "Albert Run", "Sims"]);
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const g = S.placeGroups(data.listings, data.neighborhoods.map((n) => n.name),
    (n) => S.placeForName(n, data.picker, streets, shuls, data.preferred));
  for (const name of ["Albert", "Albert Run", "Sims"]) assert.ok(g.nb.find((e) => e.name === name).ids[x.id], name);
});

// ---- Table view: click a column header to sort --------------------------------
test("sortRows: every table column sorts both ways, listings without the value stay last", () => {
  const rows = () => S.enrich([
    L({ id: "a", location: "Westgate", type: "House", rent: 3000, bedrooms_num: 4, baths: "2½" }),
    L({ id: "b", location: "13th & Princeton", type: "Apartment", rent: null, rent_display: "Call to discuss", bedrooms_num: 2, baths: "" }),
    L({ id: "c", location: "5th & Lexington", type: "Room", rent: 900, bedrooms_num: 1, baths: "1" }),
  ]);
  const ids = (mode) => S.sortRows(rows(), mode).map((x) => x.id).join("");
  assert.equal(ids("price-asc"), "cab");
  assert.equal(ids("price-desc"), "acb");               // no rent: still last
  assert.equal(ids("beds-desc"), "abc");
  assert.equal(ids("beds-asc"), "cba");
  assert.equal(ids("baths-desc"), "acb");               // no bath count: last
  assert.equal(ids("baths-asc"), "cab");
  assert.equal(ids("loc"), "cba");                      // numbers count as numbers: 5th before 13th
  assert.equal(ids("loc-desc"), "abc");
  assert.equal(ids("type-apartment"), "bac");          // apartments on top, then House, Room ...
  assert.equal(ids("type-house"), "acb");               // houses on top, then Room, Townhouse, wrapping to Apartment
  assert.equal(ids("type-room"), "cba");
  assert.equal(ids("default"), "abc");
});

test("nextColumnSort: first click is the useful direction, then reverse, then back to normal", () => {
  assert.equal(S.nextColumnSort("price", "default", false), "price-asc");
  assert.equal(S.nextColumnSort("price", "price-asc", false), "price-desc");
  assert.equal(S.nextColumnSort("price", "price-desc", false), "default");
  assert.equal(S.nextColumnSort("price", "price-desc", true), "distance");   // with a "Near" place, back to nearest first
  assert.equal(S.nextColumnSort("beds", "default", false), "beds-desc");
  assert.equal(S.nextColumnSort("beds", "price-asc", false), "beds-desc");
  assert.equal(S.nextColumnSort("loc", "default", false), "loc");
});

test("neighbourhood list: 'Outside Brookwd 1' counts under Brookwood 1 and description words are not neighbourhoods", () => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets);
  const shuls = (data.shuls || []).map((a) => ({ name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }));
  const place = S.placeForName("Outside Brookwd 1", data.picker, streets, shuls, data.preferred);
  assert.equal(place && place.name, "Brookwood 1");
  assert.ok(!(data.neighborhoods || []).some((n) => /KITCHENETTE/.test(n.name)));
});

test("type column: each click puts the next of the four types on top, then back to normal", () => {
  let mode = "default";
  const seen = [];
  for (let i = 0; i < 5; i++) { mode = S.nextColumnSort("type", mode, false); seen.push(mode); }
  assert.deepEqual(seen, ["type-apartment", "type-house", "type-room", "type-townhouse", "default"]);
  const rows = S.enrich([L({ id: "1", type: "Other" }), L({ id: "2", type: "Townhouse / Attached" }), L({ id: "3", type: "Apartment" }),
    L({ id: "4", type: "Room" }), L({ id: "5", type: "House" })]);
  assert.equal(S.sortRows(rows, "type-townhouse").map((x) => x.id).join(""), "23541");   // "Other" always last
});

test("newest first: the default order follows the issue number in each ad's code, and this week's ads are marked new", () => {
  assert.equal(S.issueNumber({ id: "11TT78_1057:7" }), 1057);
  assert.equal(S.issueNumber({ id: "A998_718:3" }), 718);
  assert.equal(S.issueNumber({ id: "p3r21" }), null);
  const rows = S.enrich([L({ id: "a_1036:1" }), L({ id: "p3r21" }), L({ id: "b_1057:1" }), L({ id: "c_1057:2" }), L({ id: "d_1056:4" }),
    L({ id: "e_1057:3" }), L({ id: "f_9999:1" })]);
  assert.deepEqual(rows.filter((x) => x._new).map((x) => x.id), ["b_1057:1", "c_1057:2", "e_1057:3", "f_9999:1"]);
  assert.equal(S.newestIssue(rows), 1057);              // one stray high number does not become "this week"
  const order = S.sortRows(rows.filter((x) => x.id !== "f_9999:1"), "default").map((x) => x.id);
  assert.deepEqual(order, ["b_1057:1", "c_1057:2", "e_1057:3", "d_1056:4", "a_1036:1", "p3r21"]);   // no code number: last
});

test("newest first on this week's list: about a batch of new ads, all at the top", () => {
  const rows = S.enrich(pagePayload().listings);
  const fresh = rows.filter((x) => x._new).length;
  assert.ok(fresh >= 3 && fresh < rows.length / 2, String(fresh));
  const sorted = S.sortRows(rows.slice(), "default");
  assert.ok(sorted.slice(0, fresh).every((x) => x._new));
});

// ---- anonymous visit and call-tap counts ---------------------------------------
test("counting: only the public site, never a device switched off with #nocount", () => {
  assert.equal(S.countsHere("lakewoodnjrentals.com", null), true);
  assert.equal(S.countsHere("www.lakewoodnjrentals.com", null), true);
  assert.equal(S.countsHere("lakewoodnjrentals.com", "t"), false);                         // this device opted out
  for (const host of ["localhost", "127.0.0.1", "", "claude.ai", "example.com"]) assert.equal(S.countsHere(host, null), false, host);
  assert.equal(S.countSwitch("#nocount"), "off");
  assert.equal(S.countSwitch("#count"), "on");
  assert.equal(S.countSwitch("#something"), null);
});

test("counting: a call tap is filed under the area, never a phone number or a street address", () => {
  assert.equal(S.callArea(L({ location: "Raintree", phones: ["732-555-0101"] })), "Raintree");
  assert.equal(S.callArea(L({ location: "13th & Princeton" })), "13th & Princeton");
  assert.equal(S.callArea(L({ location: "957 W. County Ln." })), "street address");
  assert.equal(S.callArea(L({ location: "22 Enclave Blvd.", geo_neighborhood: "enclave" })), "enclave");
  assert.equal(S.callArea(L({ location: "" })), "unknown");
  assert.doesNotMatch(S.callArea(L({ location: "Raintree", phones: ["732-555-0101"] })), /555/);
});

test("counting: the page loads the counter only through countsHere, pinned with an integrity hash, and sends no number", () => {
  assert.match(templateHtml, /if \(code && LakewoodSearch\.countsHere\(location\.hostname, flag\(\)\)\)/);
  assert.match(templateHtml, /gc\.zgo\.at\/count\.v5\.js/);
  assert.match(templateHtml, /sc\.integrity = "sha384-/);
  const call = templateHtml.slice(templateHtml.indexOf("window.goatcounter.count({"), templateHtml.indexOf("event: true });") + 20);
  assert.match(call, /data-area/);
  assert.doesNotMatch(call, /href|phone/i);
});

// ---- owner, 2026-11-26: abbreviations, areas that are also streets, 55+, addresses, nothing left out ----
const pageLists = (rows) => {
  const data = pagePayload();
  const streets = S.decodeStreets(data.streets), shuls = S.decodeShuls(data);
  const listings = S.enrich((rows || data.listings).map((x) => Object.assign({}, x)));
  const g = S.listGroups(data, listings, streets, shuls);
  const ids = (list, name) => Object.keys((g[list].find((e) => e.name === name) || { ids: {} }).ids);
  return { data, streets, shuls, listings, g, ids };
};

test("abbreviations: Rd, Ct, Ln, Rt and County Ln are read as the street words, typed or in the list", () => {
  const { data, streets, shuls } = pageLists();
  const sorts = (q) => { const r = S.placeIntent(q, data.picker, streets, shuls, data.preferred); return r && r.item.name; };
  for (const [typed, want] of [["medina rd", "Medina Road"], ["rose ct", "Rose Court"], ["shady ln", "Shady Lane"], ["rt 9", "Route 9"],
                               ["Rt.70", "Route 70"], ["county ln", "County Line Road"], ["jackson pines rd", "Jackson Pines Road"]]) {
    assert.equal(sorts(typed), want, typed);
  }
  assert.equal(S.placeForName("Spruce St.Area", data.picker, streets, shuls, data.preferred).name, "Spruce Street");
});

test("lists: Medina Road and Ridge are in both the Neighborhood and the Street list", () => {
  const rows = [L({ id: "m", location: "Medina Rd." }), L({ id: "r", location: "Ridge Area" }), L({ id: "h", location: "Heart of Ridge" }),
                L({ id: "s", location: "Shady Ln." })];
  const { ids, g } = pageLists(rows);
  assert.deepEqual(ids("nb", "Medina Road"), ["m"]);
  assert.deepEqual(ids("st", "Medina Road"), ["m"]);
  assert.deepEqual(ids("nb", "Ridge").sort(), ["h", "r"]);
  assert.deepEqual(ids("st", "Ridge Avenue").sort(), ["h", "r"]);
  assert.ok(!g.nb.some((e) => /heart of ridge|shady/i.test(e.name)));        // an ordinary street is not an area
});

test("lists: 55+ is one row (Fairways, Enclave and a vague '55+Community'), not a typed suggestion", () => {
  const { data, streets, shuls, listings, ids } = pageLists();
  const row = "55+ Communities (Fairways / Enclave)";
  const expected = listings.filter((x) => /fairways|enclave|55\+/i.test(x.location)).map((x) => x.id).sort();
  assert.deepEqual(ids("nb", row).sort(), expected);
  for (const q of ["55", "55+", "fairways", "enclave"]) {
    assert.ok(!S.suggestAll(data.picker, streets, q, 8, shuls, data.preferred).some((i) => i.name === row), q);
  }
});

test("'Fairways' is the neighbourhood, typed and in the lists, not Fairways Boulevard", () => {
  const { data, streets, shuls, listings, g, ids } = pageLists();
  const hood = "The Fairways at Lake Ridge (55+)";
  assert.equal(S.placeIntent("fairways", data.picker, streets, shuls, data.preferred).item.name, hood);
  for (const x of listings.filter((l) => l.location === "Fairways")) assert.ok(ids("nb", hood).includes(x.id));
  assert.ok(!g.st.some((e) => e.name === "Fairways Boulevard"));
  assert.ok(S.suggestAll(data.picker, streets, "fairways boulevard", 8, shuls, data.preferred).some((i) => i.name === "Fairways Boulevard"));
});

test("lists: Prime Jackson is under Jackson, an address under its neighbourhood, and no sample listing is left out", () => {
  const { listings, g, ids } = pageLists();
  for (const x of listings.filter((l) => /^prime jackson/i.test(l.location))) assert.ok(ids("nb", "Jackson").includes(x.id));
  assert.ok(!g.nb.concat(g.st).some((e) => /prime|^\d+ \w+ (blvd|ave|ln)/i.test(e.name)));
  assert.deepEqual(S.unlisted(listings, g).map((x) => x.location), []);
});
