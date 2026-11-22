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
const data = JSON.parse(fs.readFileSync(path.join(ROOT, "listings.json"), "utf8"));

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
