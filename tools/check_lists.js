#!/usr/bin/env node
// Prints a WARN line for listings that are in neither the Neighborhood nor the Street list, grouped exactly as the
// page groups them. Reads the page data (JSON) on standard input; build.py runs it after every build.
const S = require("../site/search-core.js");
const data = JSON.parse(require("fs").readFileSync(0, "utf8"));
const listings = S.enrich(data.listings || []);
const missing = S.unlisted(listings, S.listGroups(data, listings, S.decodeStreets(data.streets), S.decodeShuls(data)));
if (missing.length) {
  const names = [...new Set(missing.map((x) => x.location))];
  const shown = names.slice(0, 20).join("; ") + (names.length > 20 ? ` (+${names.length - 20} more)` : "");
  console.log(`WARN: ${missing.length} listing(s) are in neither the Neighborhood nor the Street list: ${shown}` +
    " - add the place, another spelling or a rule (see CLAUDE.md)");
}
