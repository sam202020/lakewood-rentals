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

  // ---- streets: a street is a set of lines, and "near it" means near the nearest point of any line ----

  /** Distance in miles from (lat, lng) to the segment a-b, each [lat, lng]. Flat-earth maths is exact
   *  enough over a few miles. */
  function segmentMiles(lat, lng, a, b) {
    var rad = Math.PI / 180, kx = Math.cos(lat * rad) * 69.172, ky = 69.0;
    var ax = (a[1] - lng) * kx, ay = (a[0] - lat) * ky, bx = (b[1] - lng) * kx, by = (b[0] - lat) * ky;
    var dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    var t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
    return Math.sqrt(Math.pow(ax + t * dx, 2) + Math.pow(ay + t * dy, 2));
  }

  /** Shortest distance in miles from a point to any of `paths` (a list of [[lat, lng], ...] lines). */
  function pathMiles(lat, lng, paths) {
    var best = Infinity;
    for (var i = 0; i < paths.length; i++) {
      var p = paths[i];
      if (p.length === 1) best = Math.min(best, distanceMiles(lat, lng, p[0][0], p[0][1]));
      for (var k = 0; k + 1 < p.length; k++) best = Math.min(best, segmentMiles(lat, lng, p[k], p[k + 1]));
    }
    return best;
  }

  /** Miles from where the visitor is "near" (a point, or a street's lines) to listing x. */
  /** Does the listing belong to the neighbourhood called `name` because of a shared area (Albert Run = Sims = Albert)? */
  function inArea(x, name) {
    var n = String(name || "").toLowerCase();
    return !!n && (x.areas || []).some(function (a) { return a.toLowerCase() === n; });
  }

  function originMiles(origin, x) {
    if (inArea(x, origin.name)) return 0;                       // it is in that neighbourhood, wherever its pin is
    return origin.paths && origin.paths.length
      ? pathMiles(x.lat, x.lng, origin.paths)
      : distanceMiles(origin.lat, origin.lng, x.lat, x.lng);
  }

  // ---- smarter word matching: related words, spelling variants and small typos -------------------
  //
  // People type "boy" for "bochur", "bachur" for "bocher", "synagogue" for "shul", "bsmt" for "basement".
  // Each CONCEPT is a group of words that mean (nearly) the same thing in these listings; a search word
  // matches a listing that uses ANY word of its group. Add a line here to teach the search a new group.
  // Words are compared as whole words (so "men" does not match "women" or "apartment").
  var CONCEPTS = [
    // single men / yeshiva boys
    ["bochur", "bochurim", "bachur", "bachurim", "bocher", "bocherim", "bochor", "bocur", "boy", "boys", "yeshiva boy",
     "yeshiva boys", "bachelor", "bachelors", "guy", "guys", "man", "men", "male", "males", "single man", "single men",
     "single guy", "single guys", "single male", "learning guys", "working guys", "learning men", "yungerman", "yungeleit"],
    // women / girls
    ["girl", "girls", "woman", "women", "female", "females", "lady", "ladies", "single girl", "single girls", "seminary",
     "bais yaakov", "bais yaakov girls"],
    // newlyweds
    ["choson", "chosson", "chasan", "chassan", "chosen", "kallah", "kalla", "kalah", "choson kallah", "chosson kallah",
     "newlywed", "newlyweds", "newly married", "couple", "couples", "young couple", "young couples"],
    ["shul", "shuls", "shule", "shules", "synagogue", "synagogues", "minyan", "minyanim", "beis medrash", "bais medrash",
     "beit midrash"],
    ["yeshiva", "yeshivah", "yeshivas", "yeshivos", "yeshivot", "kollel", "kollelim", "bmg", "beth medrash govoha",
     "bais medrash govoha"],
    ["shabbos", "shabbosim", "shabbat", "shabbath", "shabbes", "sabbath"],
    ["mikvah", "mikveh", "mikva", "mikvaos", "mikvahs", "mikvos"],
    ["basement", "basements", "bsmt", "bsmnt", "basemt", "bsment", "cellar", "walkout", "walk-out"],
    ["yard", "yards", "backyard", "back yard", "bkyd", "bkyard", "garden", "lawn"],
    ["bedroom", "bedrooms", "bdrm", "bdrms", "bedrm", "bedrms", "bdr", "bd", "br"],
    ["bathroom", "bathrooms", "bath", "baths", "bth", "ba"],
    ["kitchen", "kitchens", "kitchenette", "kitchenettes", "eik", "eat-in kitchen"],
    ["furnished", "furn", "furnish", "furnishing", "furnishings"],
    ["apartment", "apartments", "apt", "apts", "flat"],
    ["house", "houses", "home", "homes"],
    ["washer", "dryer", "laundry", "wd", "w/d", "washer dryer", "washer/dryer"],
    ["parking", "driveway", "driveways", "garage", "garages", "car garage"],
    ["immediately", "imm", "available now", "avail now", "available immediately", "av imm"],
    ["shortterm", "short term", "short-term", "short/long", "nightly", "per night", "weekly"],
    ["pool", "pools", "swimming pool", "heated pool", "inground pool"],
    ["studio", "studios", "efficiency"],
    ["porch", "deck", "patio", "balcony", "terrace"],
    ["renovated", "renovation", "remodeled", "remodelled", "redone"],
    ["quiet", "peaceful", "tranquil"],
    ["tenant", "tenants", "renter", "renters"],
    // 55+ communities (age-restricted): "55+", "55 plus", "over 55", "senior", ...
    ["55+", "55plus", "55 plus", "over 55", "55 and over", "55 and older", "senior", "seniors", "retirement", "retired",
     "active adult", "adult community", "age restricted"]
  ];
  var AGE55 = CONCEPTS.length - 1;               // the id of that group

  /** Lower-case word with a plural "s" removed ("shuls" -> "shul", "ladies" -> "lady"). */
  function stem(w) {
    w = String(w || "").toLowerCase();
    if (w.length > 4 && /ies$/.test(w)) return w.slice(0, -3) + "y";
    if (w.length > 3 && /s$/.test(w) && !/ss$/.test(w)) return w.slice(0, -1);
    return w;
  }

  var WORD_CONCEPTS = {};            // stemmed single word -> [concept ids]
  var PHRASES = [];                  // [{concept, text}] for the multi-word variants
  var CONCEPT_WORDS = [];            // [{w, id}] every single-word variant, for matching typos and spellings
  CONCEPTS.forEach(function (group, id) {
    group.forEach(function (item) {
      item = glueSlashes(item);
      if (item.indexOf("+") !== -1) {                // "55+": found by its text, and typed as a word
        PHRASES.push({ concept: id, text: item });
        (WORD_CONCEPTS[item] = WORD_CONCEPTS[item] || []).push(id);
      } else if (item.indexOf(" ") !== -1) PHRASES.push({ concept: id, text: item });
      else {
        (WORD_CONCEPTS[stem(item)] = WORD_CONCEPTS[stem(item)] || []).push(id);
        CONCEPT_WORDS.push({ w: stem(item), id: id });
      }
    });
  });

  /** "W/D" and "A/C" are one word: wd, ac. */
  function glueSlashes(s) { return String(s || "").toLowerCase().replace(/\b([a-z])\/([a-z])\b/g, "$1$2"); }

  function wordsOf(text) { return glueSlashes(text).match(/[a-z0-9]+/g) || []; }

  /** Say the same thing the same way before searching: "55 plus", "over 55", "55 and over", "senior community"
   *  all become "55+". */
  function normalizeQuery(q) {
    return String(q || "").toLowerCase()
      .replace(/\b(?:over\s*)?55\s*(?:\+|plus\b|and\s+(?:over|older|up)\b)/g, "55+")
      .replace(/\bover\s*55\b/g, "55+")
      .replace(/\bfifty[\s-]*five\s*(?:\+|plus\b)?/g, "55+")
      .replace(/\b(?:active|adult|senior|retirement|age[\s-]*restricted)\s+(?:communit(?:y|ies)|living|housing)\b/g, "55+")
      .replace(/\bactive\s+adults?\b/g, "55+");
  }

  var termConceptCache = {};
  /** Concept ids a typed word belongs to: by its exact word, or (6+ letters) a typo / another spelling of one
   *  of the group's words ("basment" -> basement, "bacher" -> bochur). */
  function conceptsOfTerm(term) {
    term = glueSlashes(term);
    if (termConceptCache[term]) return termConceptCache[term];
    var ids = (WORD_CONCEPTS[stem(term)] || []).slice();
    if (!ids.length && /^[a-z]+$/.test(term) && term.length >= 6) {
      var k = typoBudget(term.length), key = soundKey(term), t = stem(term);
      CONCEPT_WORDS.forEach(function (cw) {
        // only longer concept words are fuzzed: "horse" must not become "house", "pole" must not become "pool"
        if (cw.w.length < 6 || cw.w.charAt(0) !== t.charAt(0) || ids.indexOf(cw.id) !== -1) return;
        if (editDistance(t, cw.w, k) <= k ||
            (key.length >= 3 && Math.abs(cw.w.length - t.length) <= 1 && soundKey(cw.w) === key)) ids.push(cw.id);
      });
    }
    termConceptCache[term] = ids;
    return ids;
  }

  /** The other words a typed word also stands for ("boy" -> bochur, guys, men ...), for showing to the visitor. */
  function relatedWords(term) {
    var out = [], seen = {};
    conceptsOfTerm(term).forEach(function (id) {
      CONCEPTS[id].forEach(function (w) {
        if (stem(w) !== stem(term) && !seen[w]) { seen[w] = true; out.push(w); }
      });
    });
    return out;
  }

  /** Damerau-Levenshtein distance, giving up (returning max + 1) once it must exceed `max`. */
  function editDistance(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var prev2 = null, prev = [], cur, i, j, best;
    for (j = 0; j <= b.length; j++) prev[j] = j;
    for (i = 1; i <= a.length; i++) {
      cur = [i]; best = i;
      for (j = 1; j <= b.length; j++) {
        var cost = a[i - 1] === b[j - 1] ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, prev2[j - 2] + 1);
        cur[j] = v;
        if (v < best) best = v;
      }
      if (best > max) return max + 1;
      prev2 = prev; prev = cur;
    }
    return prev[b.length];
  }

  /** A rough "how it sounds" key so Hebrew/Yiddish spellings meet: bochur = bachur = bocher; chosson = chasan. */
  function soundKey(w) {
    var s = String(w || "").toLowerCase()
      .replace(/tsch|tch|sch|ch|kh/g, "H").replace(/sh/g, "S").replace(/ph/g, "f").replace(/tz|ts/g, "Z")
      .replace(/ck|q/g, "k").replace(/c(?=[eiy])/g, "s").replace(/c/g, "k").replace(/w/g, "v");
    var out = s.charAt(0);
    for (var i = 1; i < s.length; i++) {
      var ch = s.charAt(i);
      if (/[aeiouyh]/.test(ch) || ch === out.charAt(out.length - 1)) continue;
      out += ch;
    }
    return out;
  }

  function typoBudget(len) { return len >= 8 ? 2 : len >= 6 ? 1 : 0; }

  /** Does listing `x` (enriched) match the typed word `term`? Exact text first, then related words,
   *  then spelling variants / small typos. */
  function termMatches(x, term, loose) {
    term = glueSlashes(term);
    // a small bare number ("55") is a whole word, not a piece of a phone number like 732-555-0101
    if (/^\d{1,6}$/.test(term)) return x._words.indexOf(term) !== -1;
    if (x._text.indexOf(term) !== -1 && (term.length > 3 || !/^[a-z]+$/.test(term))) return true;   // as before
    var letters = /^[a-z]+$/.test(term);
    if (letters && term.length <= 3 && x._words.some(function (w) { return w.indexOf(term) === 0; })) return true;
    var ids = conceptsOfTerm(term);
    for (var i = 0; i < ids.length; i++) if (x._concepts[ids[i]]) return true;
    if (ids.indexOf(AGE55) !== -1 && x._age55) return true;      // in the Fairways / Enclave counts as 55+
    // a short word (3-5 letters) that matches nothing anywhere is probably a typo or a spelling variant ("jak"):
    // only then, accept words that start like it or sound like it
    if (loose && letters && term.length >= 3 && term.length <= 5) {
      for (var u = 0; u < x._words.length; u++) if (closeWord(term, x._words[u])) return true;
    }
    if (letters && term.length >= 6) {
      var k = typoBudget(term.length), key = soundKey(term);
      for (var w = 0; w < x._words.length; w++) {
        var word = x._words[w];
        if (word.length < 4 || word.charAt(0) !== term.charAt(0)) continue;
        if (editDistance(term, word, k) <= k) return true;
        if (key.length >= 3 && soundKey(word) === key && Math.abs(word.length - term.length) <= 1) return true;
      }
    }
    return false;
  }

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
  // ---- which listings are new ----
  // A listing's code ends in "..._1057:7": the number before the colon is the Masa U'Matan issue the ad was placed in. It stays
  // the same while the ad runs and goes up by about one a week (checked across the Aug. 26, Nov. 18 and Nov. 25 lists: 190 of
  // 194 carried-over ads kept their number, and every ad with the Nov. 25 list's top number was new that week).
  function issueNumber(x) {
    var m = /(\d{3,4}):\d+$/.exec(String(x.id || ""));
    return m ? +m[1] : null;
  }
  /** This week's issue number: the highest one that at least 3 listings share (a single garbled code must not count). */
  function newestIssue(listings) {
    var count = {}, best = null;
    listings.forEach(function (x) { var n = issueNumber(x); if (n !== null) count[n] = (count[n] || 0) + 1; });
    Object.keys(count).forEach(function (k) { if (count[k] >= 3 && (best === null || +k > best)) best = +k; });
    return best;
  }
  /** Newest first: later issue first, then the list's own order; a listing without a code number goes last. */
  function newestFirst(a, b) { return (b._issue || 0) - (a._issue || 0) || a._i - b._i; }

  function enrich(listings) {
    var newest = newestIssue(listings);
    listings.forEach(function (x, i) {
      x._i = i;
      x._issue = issueNumber(x);
      x._new = newest !== null && x._issue !== null && x._issue >= newest;
      x._baths = bathNum(x.baths);
      x._text = glueSlashes([x.location, x.comments, (x.phones || []).join(" "), x.type].join(" "));
      x._words = wordsOf(x._text).filter(function (w, i, a) { return a.indexOf(w) === i; });
      var stems = {};
      x._words.forEach(function (w) { stems[stem(w)] = true; });
      x._concepts = {};
      Object.keys(stems).forEach(function (s) { (WORD_CONCEPTS[s] || []).forEach(function (id) { x._concepts[id] = true; }); });
      PHRASES.forEach(function (p) { if (x._text.indexOf(p.text) !== -1) x._concepts[p.concept] = true; });
      // a listing is a 55+ one if it says so, or if it is in one of the 55+ communities (Fairways, Enclave)
      x._age55 = !!x._concepts[AGE55] || /\b(fairways|enclave)\b/.test(x._text);
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
      utils: new Set(), furnished: false, shortterm: false, age55: false, sort: "default",
      origin: null,   // {lat, lng}: where the visitor is, or a place they picked
      maxMiles: 0     // 0 = no distance limit
    };
  }

  /** True when listing `x` passes every active filter in state `S`. */
  function match(x, S) {
    var q = normalizeQuery(S.q).trim();
    if (q) {
      var terms = q.split(/\s+/);
      var loose = S._loose || {};
      for (var i = 0; i < terms.length; i++) if (!termMatches(x, terms[i], loose[terms[i]])) return false;
    }
    if (S.types.size && !S.types.has(x.type)) return false;
    if (S.beds && (x.bedrooms_num || 0) < S.beds) return false;
    if (S.utils.size) {
      for (var u of S.utils) if ((x.utilities_included || []).indexOf(u) === -1) return false;
    }
    if (S.furnished && !x._furnished) return false;
    if (S.shortterm && !x._short) return false;
    if (S.age55 && !x._age55) return false;
    if (x.rent == null) { if (!S.inclCall) return false; }
    else if (S.rent < NO_RENT_CAP && x.rent > S.rent) return false;
    // Distance limit: needs search() to have set _dist; listings we could not
    // place on the map never pass a distance limit.
    if (S.origin && S.maxMiles > 0 && !(typeof x._dist === "number" && x._dist <= S.maxMiles)) return false;
    return true;
  }

  // what each column sorts by; a listing without the value (no rent, no bath count) always goes last
  var SORT_KEYS = {
    price: function (x) { return x.rent; },
    beds: function (x) { return x.bedrooms_num || null; },
    baths: function (x) { return bathNum(x.baths); },
    loc: function (x) { return x.location || null; }
  };
  // The Type column stacks one kind of home on top, then the others in alphabetical order, wrapping round.
  var TYPE_ORDER = ["Apartment", "House", "Room", "Townhouse / Attached"];
  var TYPE_MODES = ["type-apartment", "type-house", "type-room", "type-townhouse"];
  function typeRank(x, first) {
    var i = TYPE_ORDER.indexOf(x.type), n = TYPE_ORDER.length;
    return i < 0 ? n : (i - first + n) % n;                       // anything else ("Other") goes last
  }

  /** Sort rows in place by `mode` and return them. Modes: "default" (newest first), "distance", a column with a direction
   *  ("price-asc", "beds-desc", "baths-desc", "loc" / "loc-desc"), or a type on top ("type-house"). Ties are newest first. */
  function sortRows(rows, mode) {
    var m = /^(price|beds|baths|loc)(?:-(asc|desc))?$/.exec(mode || ""), t = TYPE_MODES.indexOf(mode);
    rows.sort(function (a, b) {
      if (mode === "distance") {
        var ad = typeof a._dist === "number", bd = typeof b._dist === "number";
        if (ad !== bd) return ad ? -1 : 1;
        return (ad ? a._dist - b._dist : 0) || (b._own ? 1 : 0) - (a._own ? 1 : 0) || newestFirst(a, b);   // same spot: the place's own listings, then newest
      }
      if (t >= 0) return typeRank(a, t) - typeRank(b, t) || newestFirst(a, b);
      if (m) {
        var va = SORT_KEYS[m[1]](a), vb = SORT_KEYS[m[1]](b);
        var na = va === null || va === undefined, nb = vb === null || vb === undefined;
        if (na || nb) return (na ? 1 : 0) - (nb ? 1 : 0) || newestFirst(a, b);
        var d = typeof va === "string" ? va.localeCompare(vb, undefined, { numeric: true, sensitivity: "base" }) : va - vb;
        return (m[2] === "desc" ? -d : d) || newestFirst(a, b);
      }
      return newestFirst(a, b);
    });
    return rows;
  }

  // The Table view's column headers. Each click moves to the column's next order (the first is what people usually want:
  // cheapest rent, most bedrooms and bathrooms, A to Z, apartments on top); after the last one it goes back to normal.
  var COLUMN_SORTS = { loc: ["loc", "loc-desc"], type: TYPE_MODES, beds: ["beds-desc", "beds-asc"],
    baths: ["baths-desc", "baths-asc"], price: ["price-asc", "price-desc"] };
  function nextColumnSort(column, current, hasOrigin) {
    var modes = COLUMN_SORTS[column];
    if (!modes) return current;
    var i = modes.indexOf(current);
    if (i === modes.length - 1) return hasOrigin ? "distance" : "default";
    return modes[i + 1];
  }

  /** Filter then sort. Sets `_dist` (miles from S.origin) on every listing first. */
  function search(listings, S) {
    // short words that match no listing at all get the forgiving (typo / sounds-like) treatment
    var loose = {};
    normalizeQuery(S.q).trim().split(/\s+/).forEach(function (t) {
      if (/^[a-z]{3,5}$/.test(t) && !listings.some(function (x) { return termMatches(x, t, false); })) loose[t] = true;
    });
    S._loose = loose;
    var near = String(S.origin && S.origin.name || "").toLowerCase();
    listings.forEach(function (x) {
      x._dist = S.origin && hasCoords(x) ? originMiles(S.origin, x) : null;
      x._own = !!near && (inArea(x, near) || String(x.location || "").toLowerCase().indexOf(near) !== -1);   // it names the picked place
    });
    return sortRows(listings.filter(function (x) { return match(x, S); }), S.sort);
  }

  /** Keyword search that never hides the rest (owner, 2026-11-24): `matches` are the listings that pass every filter and
   *  mention the typed words; `others` pass every filter but not the words. Each group is sorted by S.sort. With no words,
   *  everything that passes the filters is a match. Sets `_kw` (true / false) on each listing. */
  function searchAll(listings, S) {
    var strict = search(listings, S), others = [];
    if (normalizeQuery(S.q).trim()) {
      var inStrict = new Set(strict), noWords = Object.assign({}, S, { q: "" });
      others = sortRows(listings.filter(function (x) { return !inStrict.has(x) && match(x, noWords); }), S.sort);
    }
    strict.forEach(function (x) { x._kw = true; });
    others.forEach(function (x) { x._kw = false; });
    return { matches: strict, others: others };
  }

  // ---- neighborhood suggestions for the combined search box ----------------------

  // Abbreviations that are not the start of the word they stand for, so matching by word start would miss them.
  // The list writes "County Ln" for County Line Road, so that one is not "lane".
  var PLACE_ABBR = { rd: "road", ct: "court", ln: "lane", rt: "route" };

  function placeTokens(s) {
    return String(s || "").toLowerCase().replace(/&/g, " ").replace(/[^a-z0-9+ ]/g, " ")
      .replace(/\b(county|cnty)\s+ln\b/g, "county line").replace(/\brt(?=\d)/g, "route ")
      .split(/\s+/).filter(Boolean)
      .map(function (w) { return PLACE_ABBR.hasOwnProperty(w) ? PLACE_ABBR[w] : w; });
  }

  /** Up to `limit` places from `picker` ([{name, lat, lng}]) that match what the visitor has typed.
   *  Best first: the name starts with the text, then every typed word starts a word of the name
   *  ("e 7" -> "E 7th Street"), then the text appears somewhere inside the name. */
  function suggestPlaces(picker, text, limit) {
    var qt = placeTokens(text);
    if (!qt.length) return [];
    var qs = qt.join(" "), out = [];
    function rank(names) {                      // best score over a place's name and its other spellings
      var best = null;
      names.forEach(function (n) {
        var lt = placeTokens(n), score = rankTokens(lt, qt);
        if (score < 0) return;
        if (!best || score < best.score) best = { score: score, len: lt.join(" ").length };
      });
      return best;
    }
    (picker || []).forEach(function (p) {
      if (p.list_only) return;                  // a row in the neighbourhood list only (55+: typing it offers the filter)
      var r = rank([p.name].concat(p.aka || []));
      if (r) out.push({ p: p, score: r.score, len: r.len });
    });
    out.sort(function (a, b) { return a.score - b.score || a.len - b.len || a.p.name.localeCompare(b.p.name); });
    if (out.length && out[0].score < 3) out = out.filter(function (o) { return o.score < 3; });   // typos only when nothing matches properly
    return out.slice(0, limit || 8).map(function (o) { return o.p; });
  }


  // ---- shuls ("near this shul"): names come from Google Maps, spelled many ways ----
  var SHUL_SPELL = { bais: "beis", beit: "beis", bes: "beis", bet: "beis", beth: "beis", medrash: "medrash", midrash: "medrash",
    medrish: "medrash", midrish: "medrash", hamedrash: "medrash", cong: "congregation", kehilas: "kehillas",
    kehilla: "kehillas", khal: "kehillas", sinagogue: "synagogue", shule: "shul" };
  // Words every shul name has; they only help when they are all the visitor typed.
  var SHUL_GENERIC = { shul: 1, shuls: 1, synagogue: 1, synagogues: 1, minyan: 1, minyanim: 1, congregation: 1, beis: 1,
    medrash: 1, of: 1, the: 1, and: 1, "d": 1, "l": 1, bnei: 1, bnai: 1 };
  function shulTokens(s) {
    return placeTokens(s).map(function (w) { return SHUL_SPELL[w] || w; });
  }

  /** Shuls ([{name, lat, lng, town, address, aka}]) matching what was typed, Lakewood first.
   *  "beis medrash" = "bais midrash"; "chabad shul" looks for Chabad. */
  function rankShuls(shuls, text, limit) {
    var qt = shulTokens(text);
    if (!qt.length || qt.join("").length < 2) return [];
    var core = qt.filter(function (w) { return !SHUL_GENERIC[w]; });
    var query = core.length ? core : qt, out = [];
    (shuls || []).forEach(function (sh) {
      var best = -1;
      [sh.name].concat(sh.aka || []).forEach(function (n) {
        var r = rankTokens(shulTokens(n), query);
        if (r >= 0 && (best < 0 || r < best)) best = r;
      });
      if (best >= 0) out.push({ s: sh, score: best });
    });
    function whole(sh) {          // every typed word is a whole word of the name ("kol" in "Kol Aryeh", not in "Kollel")
      var ws = shulTokens(sh.name);
      return query.every(function (t) { return ws.indexOf(t) !== -1; }) ? 0 : 1;
    }
    out.sort(function (a, b) {
      return a.score - b.score || whole(a.s) - whole(b.s) || (a.s.town === "Lakewood" ? 0 : 1) - (b.s.town === "Lakewood" ? 0 : 1) ||
        a.s.name.length - b.s.name.length || a.s.name.localeCompare(b.s.name);
    });
    if (out.length && out[0].score < 3) out = out.filter(function (o) { return o.score < 3; });
    return out.slice(0, limit || 8);
  }
  function suggestShuls(shuls, text, limit) {
    return rankShuls(shuls, text, limit).map(function (o) { return o.s; });
  }


  // ---- the map: one pin per spot, how unsure a spot is, a short price for the pin ----
  /** How big the "somewhere around here" circle is, in miles: a listing that only names the town could be anywhere in
   *  it (1 mi); one that names two places (averaged) is somewhere between them; a neighbourhood is a few blocks. */
  function uncertaintyMiles(x) {
    if (x.geo === "town") return x.geo_area_miles ? Math.min(1.5, Math.max(0.5, x.geo_area_miles)) : 1;   // the Jewish area of that town, as wide as the places named there
    return Math.max(0.15, (x.geo_spread || 0) / 2 + 0.1);
  }

  /** Does the list show a rent (a monthly or weekly figure) rather than "call to discuss"? */
  function hasPrice(x) {
    return x.rent != null || /^\$[\d,]+\/week$/.test(x.rent_display || "");
  }

  /** "$1,800" -> "$1.8k", "$450/week" -> "$450/wk", call-for-price -> "Call". */
  function rentLabel(x) {
    if (x.rent != null) {
      var k = x.rent / 1000;
      return x.rent >= 1000 ? "$" + (Math.round(k * 10) / 10) + "k" : "$" + x.rent;
    }
    var wk = /^\$([\d,]+)\/week$/.exec(x.rent_display || "");
    return wk ? "$" + wk[1] + "/wk" : "Call";
  }

  /** Listings with a point, grouped by that point: [{lat, lng, rows: [...]}]. Neighbourhood pins are shared by many listings. */
  function groupByPoint(rows) {
    var by = {}, out = [];
    rows.forEach(function (x) {
      if (!hasCoords(x)) return;
      var key = x.lat.toFixed(5) + "," + x.lng.toFixed(5);
      if (!by[key]) { by[key] = { lat: x.lat, lng: x.lng, rows: [] }; out.push(by[key]); }
      by[key].rows.push(x);
    });
    return out;
  }

  // ---- every street in the area (streets.json): decoding, suggestions, intersections ----

  /** The point halfway along the longest piece of a street. */
  function middleOf(paths) {
    var best = null;
    paths.forEach(function (p) {
      var len = 0;
      for (var i = 0; i + 1 < p.length; i++) len += distanceMiles(p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]);
      if (!best || len > best.len) best = { p: p, len: len };
    });
    var p = best.p, half = best.len / 2, run = 0;
    for (var i = 0; i + 1 < p.length; i++) {
      var seg = distanceMiles(p[i][0], p[i][1], p[i + 1][0], p[i + 1][1]);
      if (run + seg >= half && seg > 0) {
        var f = (half - run) / seg;
        return [p[i][0] + f * (p[i + 1][0] - p[i][0]), p[i][1] + f * (p[i + 1][1] - p[i][1])];
      }
      run += seg;
    }
    return p[0];
  }

  /** Turn the compact payload ({base, unit, towns, streets:[[name, townIndex, [path, ...]], ...]}, each path
   *  a flat list: first point, then steps) into [{n, t, paths:[[[lat, lng], ...]], lat, lng, tokens}]. */
  function decodeStreets(data) {
    if (!data || !data.streets) return [];
    var b = data.base, u = data.unit;
    return data.streets.map(function (s) {
      var paths = s[2].map(function (flat) {
        var pts = [], la = 0, ln = 0;
        for (var i = 0; i + 1 < flat.length; i += 2) {
          la += flat[i]; ln += flat[i + 1];
          pts.push([b[0] + la * u, b[1] + ln * u]);
        }
        return pts;
      });
      var mid = middleOf(paths);
      return { n: s[0], t: data.towns[s[1]], paths: paths, lat: mid[0], lng: mid[1], tokens: placeTokens(s[0]),
               dup: s[3] === 1 };
    });
  }

  function stripHouseNumber(text) {
    var m = /^\s*\d+[a-z]?\s+(?=\D)/i.exec(String(text || ""));
    return m ? String(text).slice(m[0].length) : text;
  }

  /** Is the typed word `t` (3+ letters) a typo of the start of `w`, or does it sound like the start of `w`?
   *  "jak" -> jackson (one letter off, and j-k is the start of j-k-s-n), "raintre" -> raintree, "luzk" -> lutzk. */
  function closeWord(t, w) {
    if (w.charAt(0) !== t.charAt(0)) return false;
    var k = t.length >= 7 ? 2 : t.length >= 4 ? 1 : 1;
    if (editDistance(t, w.slice(0, t.length + 1), k) <= k || editDistance(t, w, k) <= k) return true;
    var key = soundKey(t);
    return key.length >= 2 && soundKey(w).indexOf(key) === 0;
  }

  /** Spelling only (no "sounds like"): is the typed word `t` a small typo of `w`, or of the start of `w`? */
  function editClose(t, w) {
    if (w.charAt(0) !== t.charAt(0)) return false;
    var k = t.length >= 7 ? 2 : 1;
    return editDistance(t, w.slice(0, t.length + 1), k) <= k || editDistance(t, w, k) <= k;
  }

  function rankTokens(tokens, qt) {
    var label = tokens.join(" "), qs = qt.join(" ");
    if (label.indexOf(qs) === 0) return 0;
    if (qt.every(function (t) { return tokens.some(function (w) { return w.indexOf(t) === 0; }); })) return 1;
    if ((" " + label).indexOf(" " + qs) !== -1) return 2;               // typed words start a word of the name (not the middle of one: "pool" is not Liverpool)
    // a small typo or another spelling ("raintre", "luzk", "clifto", "jak" for Jackson): every typed word is close
    // to a word of the name, in spelling or in sound. Numbers ("13th") are never "corrected".
    if (qt.every(function (t) {
      if (/\d/.test(t) || t.length < 3) return false;
      return tokens.some(function (w) { return closeWord(t, w); });
    })) return closeWord(qt[0], tokens[0]) ? 3 : 3.5;                    // the name's own first word beats a word in the middle
    return -1;
  }

  /** Best rankTokens over a place's name and its other spellings (-1 = no match). */
  function bestRank(names, qt) {
    var best = -1;
    names.forEach(function (n) {
      var r = rankTokens(placeTokens(n), qt);
      if (r >= 0 && (best < 0 || r < best)) best = r;
    });
    return best;
  }

  /** Streets matching what was typed (a leading house number is ignored: "415 laurel ave" -> laurel ave). */
  function suggestStreets(streets, text, limit, withDuplicates) {
    var qt = placeTokens(stripHouseNumber(text));
    if (!qt.length || qt.join("").length < 2) return [];
    var out = [];
    (streets || []).forEach(function (s) {
      if (s.dup && !withDuplicates) return;        // already offered as an owner-defined neighborhood
      var r = rankTokens(s.tokens, qt);
      if (r >= 0) out.push({ s: s, score: r, len: s.tokens.join(" ").length });
    });
    // best match first; among equally good matches Lakewood's own streets come first, then the nearest to Lakewood
    var core = [40.0979, -74.2179];
    function away(s) { return distanceMiles(core[0], core[1], s.lat, s.lng); }
    function home(s) { return s.t === "Lakewood" ? 0 : 1; }
    out.sort(function (a, b) {
      return a.score - b.score || home(a.s) - home(b.s) || a.len - b.len || away(a.s) - away(b.s) || a.s.n.localeCompare(b.s.n);
    });
    if (out.length && out[0].score < 3) out = out.filter(function (o) { return o.score < 3; });
    return out.slice(0, limit || 8).map(function (o) { return o.s; });
  }

  /** Closest approach of two segments (each [[lat, lng], [lat, lng]]): where they cross, else the nearest end. */
  function segmentPair(a, b) {
    var rad = Math.PI / 180, lat0 = a[0][0], kx = Math.cos(lat0 * rad) * 69.172, ky = 69.0;
    function xy(p) { return [(p[1] - a[0][1]) * kx, (p[0] - lat0) * ky]; }
    var p = xy(a[0]), r = xy(a[1]), q = xy(b[0]), s = xy(b[1]);
    var rx = r[0] - p[0], ry = r[1] - p[1], sx = s[0] - q[0], sy = s[1] - q[1];
    var den = rx * sy - ry * sx;
    if (den) {
      var t = ((q[0] - p[0]) * sy - (q[1] - p[1]) * sx) / den, u = ((q[0] - p[0]) * ry - (q[1] - p[1]) * rx) / den;
      if (t >= 0 && t <= 1 && u >= 0 && u <= 1) {
        return { d: 0, lat: a[0][0] + t * (a[1][0] - a[0][0]), lng: a[0][1] + t * (a[1][1] - a[0][1]) };
      }
    }
    var best = null;
    [[a[0], b], [a[1], b], [b[0], a], [b[1], a]].forEach(function (c) {
      var d = segmentMiles(c[0][0], c[0][1], c[1][0], c[1][1]);
      if (!best || d < best.d) best = { d: d, lat: c[0][0], lng: c[0][1] };
    });
    return best;
  }

  /** Where two streets cross (or nearly): the closest approach between their lines, or null if > maxMiles. */
  function crossing(a, b, maxMiles) {
    var best = null;
    a.paths.forEach(function (pa) {
      for (var i = 0; i + 1 < pa.length; i++) {
        b.paths.forEach(function (pb) {
          for (var k = 0; k + 1 < pb.length; k++) {
            var c = segmentPair([pa[i], pa[i + 1]], [pb[k], pb[k + 1]]);
            if (!best || c.d < best.d) best = c;
          }
        });
      }
    });
    return best && best.d <= (maxMiles || 0.12) ? best : null;
  }

  /** "Clover & Ocean", "ridge and nowlan", "oak / vine": the intersections of the streets named. */
  function suggestCrossings(streets, text, limit) {
    var parts = String(text || "").split(/\s*(?:&|\/|@|\band\b)\s*/i).filter(function (p) { return p.trim(); });
    if (parts.length !== 2) return [];
    var as = suggestStreets(streets, parts[0], 6, true), bs = suggestStreets(streets, parts[1], 6, true), out = [];
    as.forEach(function (a) {
      bs.forEach(function (b) {
        if (a === b) return;
        var c = crossing(a, b);
        if (c) out.push({ name: a.n + " & " + b.n, town: a.t, lat: c.lat, lng: c.lng, d: c.d });
      });
    });
    out.sort(function (x, y) { return x.d - y.d || x.name.localeCompare(y.name); });
    return out.slice(0, limit || 3);
  }

  /** The suggestion list for the search box: [{kind: "place"|"street"|"cross", ...}], best first.
   *  Neighborhoods the owner defined come before streets with an equally good match. */
  function suggestAll(picker, streets, text, limit, shuls, preferred) {
    limit = limit || 8;
    var typed = String(text || "").trim().toLowerCase();
    text = canonicalText(text);
    var items = [];
    // "55", "55+", "55 plus", "senior", "over 55" ... offer the 55+ communities as a topic, not a place
    var norm = normalizeQuery(text).trim();
    if (norm && (/^(55\+?|sen|ret|adu|age)/.test(norm) || norm === "55+")) {
      items.push({ kind: "topic", name: "55+ communities", topic: "age55", note: "show only 55+ listings" });
    }
    // "shul", "synagogue", "minyan" ... : the visitor has the right idea, tell them to type a shul's name
    if (/^(shuls?|shules?|synagogues?|minyan(im)?|beis medrash|bais medrash|beit midrash|beis midrash)$/.test(String(text || "").trim().toLowerCase())) {
      items.push({ kind: "hint", name: "Type a shul\u2019s name", note: "e.g. Kol Aryeh, BMG, Spruce Street", fill: "Kol Aryeh" });
    }
    suggestCrossings(streets, text, 2).forEach(function (c) { items.push({ kind: "cross", name: c.name, town: c.town, lat: c.lat, lng: c.lng }); });
    var qt = placeTokens(text), places = suggestPlaces(picker, text, limit);
    places.forEach(function (p) { items.push({ kind: "place", name: p.name, town: p.town, lat: p.lat, lng: p.lng, score: 0, shul: !!p.shul, aka: p.aka || [] }); });
    var seen = {};
    items.forEach(function (it) { seen[it.name.toLowerCase()] = true; });
    suggestStreets(streets, text, limit).forEach(function (s) {
      if (seen[(s.n + " " + s.t).toLowerCase()]) return;
      items.push({ kind: "street", name: s.n, town: s.t, lat: s.lat, lng: s.lng, paths: s.paths });
    });
    rankShuls(shuls, text, limit).forEach(function (o) {
      items.push({ kind: "shul", name: o.s.name, town: o.s.town, address: o.s.address, lat: o.s.lat, lng: o.s.lng, aka: o.s.aka || [], _shulRank: o.score });
    });
    // keep places ahead of streets only as a tie-break: re-rank everything by match quality
    if (qt.length) {
      items.forEach(function (it, i) {
        var r = it.kind === "cross" || it.kind === "topic" || it.kind === "hint" ? -1 : it.kind === "shul" ? it._shulRank : bestRank([it.name].concat(it.aka || []), qt);
        it._r = it.kind === "cross" || it.kind === "topic" || it.kind === "hint" ? -1 : (r < 0 ? 3 : r);       // topics and intersections lead
        it._o = i;
      });
      items.sort(function (a, b) { return a._r - b._r || a._o - b._o; });
      if (items.length && items[0]._r < 3) items = items.filter(function (it) { return it._r < 3; });   // typo matches only as a last resort
    }
    // a street word that fits many streets: the one people mean goes first ("forest" -> Forest Avenue, Lakewood)
    var prefKey = preferred && preferred[typed] ? typed : null, fuzzyPref = false;
    if (!prefKey && preferred && /^[a-z]{4,}$/.test(typed) && !items.some(function (it) { return it._r >= 0 && it._r < 3; })) {
      Object.keys(preferred).forEach(function (k) { if (!prefKey && editClose(typed, k)) { prefKey = k; fuzzyPref = true; } });   // "foreset" -> forest
    }
    var want = prefKey && preferred[prefKey];
    if (want) {
      var pick = null;
      (streets || []).forEach(function (s) { if (!pick && s.n === want && s.t === "Lakewood") pick = s; });
      if (pick) {
        items = items.filter(function (it) { return !(it.kind === "street" && it.name === pick.n && it.town === pick.t); });
        items.unshift({ kind: "street", name: pick.n, town: pick.t, lat: pick.lat, lng: pick.lng, paths: pick.paths, _r: 0, _pref: true, _fuzzy: fuzzyPref });
      }
    }
    return items.slice(0, limit);
  }

    // ---- what does the typed text mean? A place (sort by distance) or a word (filter the listings) ----
  var GENERIC_ONLY = /^(shuls?|shules?|synagogues?|minyan(im)?|beis medrash|bais medrash|beit midrash|beis midrash)$/;

  /** Words that people use for one place: "yeshiva" on its own means BMG (owner, 2026-11-24). */
  var WORD_FOR_PLACE = /^yeshiv(a|ah|as|os)$/;
  function canonicalText(text) {
    var t = String(text || "").trim();
    return WORD_FOR_PLACE.test(t.toLowerCase()) ? "bmg" : text;
  }

  /** The first place a location names, "Area" dropped: what the listing is grouped under (as geo.neighborhood_display_name). */
  function firstName(location) {
    return String(location || "").split(/\s*\/\s*|,\s*/)[0].replace(/\s+Area$/i, "").trim();
  }

  var STREET_NAME = /\b(street|st|avenue|ave|drive|dr|road|rd|lane|ln|court|ct|boulevard|blvd|place|pl|way|terrace|circle|route|rt)\.?$/i;

  /** The neighbourhood and street lists (drop-down browse lists and the Table view's side list, which must agree).
   *  names = every location name ever listed; resolve(name) = the place it stands for, or null; areaStreets =
   *  {street name: area name} for streets people also mean as an area, which go in both lists. Names meaning the same
   *  place merge; a listing counts once under its first place name and under every area it also belongs to.
   *  -> { nb: [{name, town, item, n, ids}], st: [...] }, each sorted by name. */
  function placeGroups(listings, names, resolve, areaStreets) {
    var byName = {}, groups = { nb: {}, st: {} };
    function groupsFor(raw) {
      if (byName.hasOwnProperty(raw)) return byName[raw];
      var it = resolve(raw), found = [];
      function add(cls, item) {
        var key = item.name + "|" + (item.town || "");
        found.push(groups[cls][key] || (groups[cls][key] = { name: item.name, town: item.town, item: item, n: 0, ids: {} }));
      }
      if (it) {
        var area = areaStreets && (it.town || "Lakewood") === "Lakewood" && areaStreets.hasOwnProperty(it.name) && areaStreets[it.name];
        var cls = it.kind === "street" || it.kind === "cross" || /&/.test(raw) || STREET_NAME.test(it.name) || /^\d+(st|nd|rd|th)\b/i.test(it.name) ? "st" : it.kind === "place" ? "nb" : "";
        if (area) {
          var asArea = {};
          Object.keys(it).forEach(function (k) { asArea[k] = it[k]; });
          asArea.name = area;
          add("st", it);
          add("nb", asArea);
        } else if (cls) add(cls, it);
      }
      return (byName[raw] = found);
    }
    (names || []).forEach(groupsFor);                               // names with no listing this week stay, with 0
    (listings || []).forEach(function (x) {
      [firstName(x.location)].concat(x.areas || []).forEach(function (raw) {
        (raw ? groupsFor(raw) : []).forEach(function (g) {
          if (!g.ids[x.id]) { g.ids[x.id] = true; g.n++; }
        });
      });
    });
    function sorted(o) { return Object.keys(o).map(function (k) { return o[k]; }).sort(function (a, b) { return a.name.localeCompare(b.name); }); }
    return { nb: sorted(groups.nb), st: sorted(groups.st) };
  }

  /** The shuls embedded in the page, as objects. */
  function decodeShuls(data) {
    return ((data && data.shuls) || []).map(function (a) { return { name: a[0], lat: a[1], lng: a[2], town: a[3], address: a[4], aka: a[5] || [] }; });
  }

  /** The lists as the page shows them, from the page data (`streets` and `shuls` already decoded). */
  function listGroups(data, listings, streets, shuls) {
    return placeGroups(listings, (data.neighborhoods || []).map(function (n) { return n.name; }),
      function (name) { return placeForName(name, data.picker, streets, shuls, data.preferred || {}); }, data.area_streets || {});
  }

  /** Listings that are in neither list (the build warns about them). */
  function unlisted(listings, groups) {
    var counted = {};
    groups.nb.concat(groups.st).forEach(function (g) { Object.keys(g.ids).forEach(function (id) { counted[id] = true; }); });
    return listings.filter(function (x) { return !counted[x.id]; });
  }

  /** The place a listing's location name stands for, for the browse lists. The PDF adds words that say where the
   *  place is, not what it is ("New Prospect Jackson", "Mackenzie Area Toms River", "Off Chestnut"): when the name as
   *  written is not a place, try it without them. A trailing town is dropped only if a name remains. */
  var AROUND_WORDS = /\b(area|near|off|outside)\b/gi, TRAILING_TOWN = /[\s,]+(lakewood|jackson|toms river|howell|manchester|brick)\s*$/i;
  function placeForName(name, picker, streets, shuls, preferred) {
    function full(words) {                      // "Spruce St." is Spruce Street
      return placeTokens(canonicalText(words)).map(function (w) { return w === "st" ? "street" : w === "ave" ? "avenue" : w; }).join(" ");
    }
    function isCalled(item, words) {
      var want = full(words);
      return [item.name].concat(item.aka || []).some(function (n) { return full(n) === want; });
    }
    var listed = (picker || []).filter(function (p) { return p.list_only && isCalled(p, name); })[0];
    if (listed) return { kind: "place", name: listed.name, town: listed.town, lat: listed.lat, lng: listed.lng, aka: listed.aka || [] };
    var bare = String(name || "").replace(AROUND_WORDS, " ").replace(/\s+/g, " ").trim();
    var tries = [String(name || ""), bare, bare.replace(TRAILING_TOWN, "")];
    for (var i = 0; i < tries.length; i++) {
      if (i && tries[i] === tries[i - 1]) continue;
      var r = placeIntent(tries[i], picker, streets, shuls, preferred);
      if (r && !r.rest && (i === 0 || isCalled(r.item, tries[i]))) return r.item;     // trimmed names must match exactly ("Prime" is not Prime Lane)
    }
    return null;
  }

  /** The best place for `text` if the text (a prefix of) names one: {item, rest} where rest is leftover keyword words
   *  ("raintree pool" -> Raintree + "pool"), else null. Needs 3+ letters. Streets, neighborhoods, shuls and intersections count;
   *  typo matches, "55+", the bare words shul/yeshiva and single words that mean something in a listing (pool, boy, basement)
   *  do not. The dropdown shows the same items, so what is sorted by is always the first suggestion. */
  function placeIntent(text, picker, streets, shuls, preferred) {
    var typedRaw = String(text || "").trim().toLowerCase();
    var t = canonicalText(text).trim().toLowerCase();
    if (t.replace(/[^a-z0-9]/g, "").length < 3 || GENERIC_ONLY.test(t)) return null;
    function best(s, exact) {
      var qt = placeTokens(s);
      if (!qt.length) return null;
      var items = suggestAll(picker, streets, s, 8, shuls, s === t ? preferred : null);
      for (var i = 0; i < items.length; i++) {
        var it = items[i];
        if (it.kind === "topic" || it.kind === "hint") return null;
        if (it.kind === "cross") return it;
        if (it._pref) return it;                                         // the street people mean by that word (also for a typo of it)
        if (it._r > 1) return null;                                      // typo / sounds-like matches are not a place
        if (it.kind === "street" || (it.kind === "shul" && !exact)) {    // "forest" could be Forest Avenue, Drive, Hills ...: a street (or a shul the street names compete with) needs words that single it out
          var names = {};
          items.forEach(function (o) { if (o.kind === "street" && o._r <= it._r) names[o.name.toLowerCase()] = true; });   // streets as good a match as this one
          if (Object.keys(names).length > 1) return null;
        }
        if (exact) {
          var labels = [it.name].concat(it.aka || []).map(function (n) { return placeTokens(n).join(" "); });
          if (labels.indexOf(qt.join(" ")) === -1) return null;
        }
        return it;
      }
      return null;
    }
    var words = t.split(/\s+/), it = best(t, false);
    if (it) {
      // a single word that also means something in a listing (pool, boy, basement ...) stays a keyword unless it is a place's exact name
      if (words.length === 1 && conceptsOfTerm(words[0]).length && !(words[0].length >= 6 && it._r === 0)) {
        var exact = best(t, true);
        return exact ? { item: exact, rest: "" } : null;
      }
      return { item: it, rest: "", typo: !!it._fuzzy };
    }
    for (var k = words.length - 1; k >= 1; k--) {                          // leading words that exactly name a place + keyword words
      var head = words.slice(0, k).join(" "), h = best(head, true);
      if (h) return { item: h, rest: words.slice(k).join(" ") };
    }
    for (var j = 1; j < words.length; j++) {                               // ... or keyword words + the place at the end
      var tail = words.slice(j).join(" "), g = best(tail, true);
      if (g) return { item: g, rest: words.slice(0, j).join(" ") };
    }
    // a typo of a place ("raintre", "spruse street", "kol aryeh" spelt oddly) is that place, unless the words are ones the listings use
    if (words.every(function (w) { return !/\d/.test(w) && w.length >= 3 && !conceptsOfTerm(w).length; })) {
      var items = suggestAll(picker, streets, t, 8, shuls, preferred);
      for (var m = 0; m < items.length; m++) {
        var ty = items[m];
        if (ty.kind === "topic" || ty.kind === "hint" || ty.kind === "keyword" || ty.kind === "cross" || ty._r < 3) return null;
        var tyWords = placeTokens([ty.name].concat(ty.aka || []).join(" "));
        var spelt = words.every(function (w) { return tyWords.some(function (n) { return n === w || editClose(w, n); }); });   // a real misspelling, not just a similar sound
        if (!spelt) continue;
        if (ty.kind === "street") {
          var nm = {};
          items.forEach(function (o) { if (o.kind === "street" && o._r <= ty._r) nm[o.name.toLowerCase()] = true; });
          if (Object.keys(nm).length > 1) return null;
        }
        return { item: ty, rest: "", typo: true };
      }
    }
    return null;
  }

  // ---- anonymous counts: visits and call taps, the public site only ----
  var PUBLIC_HOSTS = ["lakewoodnjrentals.com", "www.lakewoodnjrentals.com"];

  /** Count this visit? Only on the public site (not local copies, previews or the private page), and never on a device
   *  that was switched off (`flag` is what localStorage "skipgc" holds: "t" means do not count). */
  function countsHere(host, flag) { return PUBLIC_HOSTS.indexOf(String(host || "").toLowerCase()) !== -1 && flag !== "t"; }

  /** "#nocount" switches this device off, "#count" back on. */
  function countSwitch(hash) { return hash === "#nocount" ? "off" : hash === "#count" ? "on" : null; }

  /** What a call tap is filed under: the listing's area. Never a phone number, and a street address is not passed on. */
  function callArea(x) {
    if (x.geo_neighborhood) return String(x.geo_neighborhood);
    var loc = String(x.location || "").trim();
    if (!loc) return "unknown";
    return /^\d+[a-z]?\s/i.test(loc) ? "street address" : loc;
  }

  /** How many filter groups (not counting the search box, the distance chip or the visible 55+ chip) are switched on. */
  function activeFilterCount(S) {
    return (S.types.size ? 1 : 0) + (S.beds ? 1 : 0) + (S.rent < NO_RENT_CAP ? 1 : 0) +
      (S.inclCall ? 0 : 1) + (S.utils.size ? 1 : 0) + (S.furnished ? 1 : 0) + (S.shortterm ? 1 : 0);
  }

  return {
    NO_RENT_CAP: NO_RENT_CAP,
    suggestPlaces: suggestPlaces,
    normalizeQuery: normalizeQuery,
    closeWord: closeWord,
    CONCEPTS: CONCEPTS,
    relatedWords: relatedWords,
    editDistance: editDistance,
    soundKey: soundKey,
    termMatches: termMatches,
    suggestStreets: suggestStreets,
    suggestShuls: suggestShuls,
    suggestCrossings: suggestCrossings,
    suggestAll: suggestAll,
    placeIntent: placeIntent,
    placeForName: placeForName,
    placeGroups: placeGroups,
    firstName: firstName,
    decodeStreets: decodeStreets,
    decodeShuls: decodeShuls,
    listGroups: listGroups,
    unlisted: unlisted,
    uncertaintyMiles: uncertaintyMiles,
    rentLabel: rentLabel,
    hasPrice: hasPrice,
    groupByPoint: groupByPoint,
    pathMiles: pathMiles,
    originMiles: originMiles,
    crossing: crossing,
    activeFilterCount: activeFilterCount,
    TAGRULES: TAGRULES,
    bathNum: bathNum,
    distanceMiles: distanceMiles,
    enrich: enrich,
    defaultState: defaultState,
    match: match,
    sortRows: sortRows,
    nextColumnSort: nextColumnSort,
    issueNumber: issueNumber,
    newestIssue: newestIssue,
    TYPE_ORDER: TYPE_ORDER,
    COLUMN_SORTS: COLUMN_SORTS,
    countsHere: countsHere,
    countSwitch: countSwitch,
    callArea: callArea,
    search: search,
    searchAll: searchAll
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = LakewoodSearch;
