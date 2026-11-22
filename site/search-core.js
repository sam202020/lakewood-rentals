/* Search + filter logic for the Lakewood NJ Area Rentals page.
 *
 * Pure functions with no DOM access, so they can be unit-tested in Node
 * (tests/search.test.js). build.py inlines this file into the page at the
 * /*__SEARCH_CORE__*\/ marker in site/template.html.
 */
var LakewoodSearch = (function () {
  "use strict";

  var NO_RENT_CAP = 7000; // slider maximum: "Any"

  function bathNum(s) {
    if (!s) return null;
    var m = String(s).match(/(\d+)/);
    var n = m ? +m[1] : 0;
    if (/[½]/.test(s)) n += 0.5;
    if (/[¼]/.test(s)) n += 0.25;
    if (/[¾]/.test(s)) n += 0.75;
    return n || null;
  }

  /** Great-circle distance in miles. */
  function distanceMiles(lat1, lng1, lat2, lng2) {
    var rad = Math.PI / 180, R = 3958.8;
    var dLat = (lat2 - lat1) * rad, dLng = (lng2 - lng1) * rad;
    var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function hasCoords(x) { return typeof x.lat === "number" && typeof x.lng === "number"; }

  var SHORT_RE = /short[\s-]?term|short\/long|weekly|nightly|\/night|per night/i;

  // [label, pattern, highlight]
  var TAGRULES = [
    ["Choson / Kallah", /choson|chosson|chas[sa]n|kalla/i, false],
    ["Short-term OK", /short[\s-]?term|short\/long|weekly|nightly|per night|\/night/i, false],
    ["Long-term", /long[\s-]?term|long\/short|\byear\b|10[\s-]?month|annual/i, false],
    ["Available now", /available imm|av\.? ?imm|immediately|avail\. now/i, false],
    ["Pool", /\bpool\b/i, false],
    ["Office use", /\boffice\b/i, false],
    ["Basement", /basement|bsmt/i, false],
    ["Backyard", /back ?yard|bkyd|\byard\b/i, false]
  ];

  /** Add the derived (_-prefixed) fields the filters rely on. Mutates and returns the list. */
  function enrich(listings) {
    listings.forEach(function (x, i) {
      x._i = i;
      x._baths = bathNum(x.baths);
      x._text = [x.location, x.comments, (x.phones || []).join(" "), x.type].join(" ").toLowerCase();
      x._furnished = !!x.furnished || /furnish/i.test(x.comments || "");
      x._short = SHORT_RE.test(x.comments || "");
      x._tags = [];
      TAGRULES.forEach(function (r) {
        if (r[1].test(x.comments || "")) x._tags.push([r[0], r[2]]);
      });
    });
    return listings;
  }

  function defaultState() {
    return {
      q: "", types: new Set(), beds: 0, rent: NO_RENT_CAP, inclCall: true,
      utils: new Set(), furnished: false, shortterm: false, sort: "default",
      origin: null,   // {lat, lng}: where the visitor is, or a place they picked
      maxMiles: 0     // 0 = no distance limit
    };
  }

  /** True when listing `x` passes every active filter in state `S`. */
  function match(x, S) {
    var q = String(S.q || "").toLowerCase().trim();
    if (q) {
      var terms = q.split(/\s+/);
      for (var i = 0; i < terms.length; i++) if (x._text.indexOf(terms[i]) === -1) return false;
    }
    if (S.types.size && !S.types.has(x.type)) return false;
    if (S.beds && (x.bedrooms_num || 0) < S.beds) return false;
    if (S.utils.size) {
      for (var u of S.utils) if ((x.utilities_included || []).indexOf(u) === -1) return false;
    }
    if (S.furnished && !x._furnished) return false;
    if (S.shortterm && !x._short) return false;
    if (x.rent == null) { if (!S.inclCall) return false; }
    else if (S.rent < NO_RENT_CAP && x.rent > S.rent) return false;
    // Distance limit: needs search() to have set _dist; listings we could not
    // place on the map never pass a distance limit.
    if (S.origin && S.maxMiles > 0 && !(typeof x._dist === "number" && x._dist <= S.maxMiles)) return false;
    return true;
  }

  /** Sort rows in place by `mode` and return them. Listings with no rent (or, for
   *  "distance", no map position) always sort last. */
  function sortRows(rows, mode) {
    rows.sort(function (a, b) {
      if (mode === "distance") {
        var ad = typeof a._dist === "number", bd = typeof b._dist === "number";
        if (ad !== bd) return ad ? -1 : 1;
        return (ad ? a._dist - b._dist : 0) || a._i - b._i;
      }
      if (mode === "price-asc") return (a.rent == null) - (b.rent == null) || (a.rent || 0) - (b.rent || 0);
      if (mode === "price-desc") return (a.rent == null) - (b.rent == null) || (b.rent || 0) - (a.rent || 0);
      if (mode === "beds-desc") return (b.bedrooms_num || 0) - (a.bedrooms_num || 0) || a._i - b._i;
      if (mode === "loc") return (a.location || "~").localeCompare(b.location || "~");
      return a._i - b._i;
    });
    return rows;
  }

  /** Filter then sort. Sets `_dist` (miles from S.origin) on every listing first. */
  function search(listings, S) {
    listings.forEach(function (x) {
      x._dist = S.origin && hasCoords(x)
        ? distanceMiles(S.origin.lat, S.origin.lng, x.lat, x.lng) : null;
    });
    return sortRows(listings.filter(function (x) { return match(x, S); }), S.sort);
  }

  return {
    NO_RENT_CAP: NO_RENT_CAP,
    TAGRULES: TAGRULES,
    bathNum: bathNum,
    distanceMiles: distanceMiles,
    enrich: enrich,
    defaultState: defaultState,
    match: match,
    sortRows: sortRows,
    search: search
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = LakewoodSearch;
