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
  function originMiles(origin, x) {
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
    ["tenant", "tenants", "renter", "renters"]
  ];

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
      if (item.indexOf(" ") !== -1) PHRASES.push({ concept: id, text: item });
      else {
        (WORD_CONCEPTS[stem(item)] = WORD_CONCEPTS[stem(item)] || []).push(id);
        CONCEPT_WORDS.push({ w: stem(item), id: id });
      }
    });
  });

  /** "W/D" and "A/C" are one word: wd, ac. */
  function glueSlashes(s) { return String(s || "").toLowerCase().replace(/\b([a-z])\/([a-z])\b/g, "$1$2"); }

  function wordsOf(text) { return glueSlashes(text).match(/[a-z0-9]+/g) || []; }

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
  function termMatches(x, term) {
    term = glueSlashes(term);
    if (x._text.indexOf(term) !== -1 && (term.length > 3 || !/^[a-z]+$/.test(term))) return true;   // as before
    var letters = /^[a-z]+$/.test(term);
    if (letters && term.length <= 3 && x._words.some(function (w) { return w.indexOf(term) === 0; })) return true;
    var ids = conceptsOfTerm(term);
    for (var i = 0; i < ids.length; i++) if (x._concepts[ids[i]]) return true;
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
  function enrich(listings) {
    listings.forEach(function (x, i) {
      x._i = i;
      x._baths = bathNum(x.baths);
      x._text = glueSlashes([x.location, x.comments, (x.phones || []).join(" "), x.type].join(" "));
      x._words = wordsOf(x._text).filter(function (w, i, a) { return a.indexOf(w) === i; });
      var stems = {};
      x._words.forEach(function (w) { stems[stem(w)] = true; });
      x._concepts = {};
      Object.keys(stems).forEach(function (s) { (WORD_CONCEPTS[s] || []).forEach(function (id) { x._concepts[id] = true; }); });
      PHRASES.forEach(function (p) { if (x._text.indexOf(p.text) !== -1) x._concepts[p.concept] = true; });
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
      for (var i = 0; i < terms.length; i++) if (!termMatches(x, terms[i])) return false;
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
      x._dist = S.origin && hasCoords(x) ? originMiles(S.origin, x) : null;
    });
    return sortRows(listings.filter(function (x) { return match(x, S); }), S.sort);
  }

  // ---- neighborhood suggestions for the combined search box ----------------------

  function placeTokens(s) {
    return String(s || "").toLowerCase().replace(/&/g, " ").replace(/[^a-z0-9+ ]/g, " ")
      .split(/\s+/).filter(Boolean);
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
      var r = rank([p.name].concat(p.aka || []));
      if (r) out.push({ p: p, score: r.score, len: r.len });
    });
    out.sort(function (a, b) { return a.score - b.score || a.len - b.len || a.p.name.localeCompare(b.p.name); });
    return out.slice(0, limit || 8).map(function (o) { return o.p; });
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

  function rankTokens(tokens, qt) {
    var label = tokens.join(" "), qs = qt.join(" ");
    if (label.indexOf(qs) === 0) return 0;
    if (qt.every(function (t) { return tokens.some(function (w) { return w.indexOf(t) === 0; }); })) return 1;
    if (label.indexOf(qs) !== -1) return 2;
    // a small typo or another spelling ("raintre", "luzk", "clifto"): every typed word is close to a word of the name
    if (qt.every(function (t) {
      var k = /\d/.test(t) ? 0 : t.length >= 7 ? 2 : t.length >= 4 ? 1 : 0;      // numbers ("13th") are never "corrected"
      return k > 0 && tokens.some(function (w) {
        return w.charAt(0) === t.charAt(0) &&
          (editDistance(t, w.slice(0, t.length + 1), k) <= k || editDistance(t, w, k) <= k);
      });
    })) return 3;
    return -1;
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
  function suggestAll(picker, streets, text, limit) {
    limit = limit || 8;
    var items = [];
    suggestCrossings(streets, text, 2).forEach(function (c) { items.push({ kind: "cross", name: c.name, town: c.town, lat: c.lat, lng: c.lng }); });
    var qt = placeTokens(text), places = suggestPlaces(picker, text, limit);
    places.forEach(function (p) { items.push({ kind: "place", name: p.name, lat: p.lat, lng: p.lng, score: 0 }); });
    var seen = {};
    items.forEach(function (it) { seen[it.name.toLowerCase()] = true; });
    suggestStreets(streets, text, limit).forEach(function (s) {
      if (seen[(s.n + " " + s.t).toLowerCase()]) return;
      items.push({ kind: "street", name: s.n, town: s.t, lat: s.lat, lng: s.lng, paths: s.paths });
    });
    // keep places ahead of streets only as a tie-break: re-rank everything by match quality
    if (qt.length) {
      items.forEach(function (it, i) {
        var r = it.kind === "cross" ? -1 : rankTokens(placeTokens(it.name), qt);
        it._r = r < 0 ? 3 : r;
        it._o = i;
      });
      items.sort(function (a, b) { return a._r - b._r || a._o - b._o; });
    }
    return items.slice(0, limit);
  }

  /** How many filter groups (not counting the search box or the distance chip) are switched on. */
  function activeFilterCount(S) {
    return (S.types.size ? 1 : 0) + (S.beds ? 1 : 0) + (S.rent < NO_RENT_CAP ? 1 : 0) +
      (S.inclCall ? 0 : 1) + (S.utils.size ? 1 : 0) + (S.furnished ? 1 : 0) + (S.shortterm ? 1 : 0);
  }

  return {
    NO_RENT_CAP: NO_RENT_CAP,
    suggestPlaces: suggestPlaces,
    CONCEPTS: CONCEPTS,
    relatedWords: relatedWords,
    editDistance: editDistance,
    soundKey: soundKey,
    termMatches: termMatches,
    suggestStreets: suggestStreets,
    suggestCrossings: suggestCrossings,
    suggestAll: suggestAll,
    decodeStreets: decodeStreets,
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
    search: search
  };
})();

if (typeof module !== "undefined" && module.exports) module.exports = LakewoodSearch;
