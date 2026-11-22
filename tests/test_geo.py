"""Tests for location -> coordinates (geo.py) and its use in the build.

Run:  python3 -m unittest discover -s tests -v
"""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: E402
import geo  # noqa: E402

PLACES = {
    "raintree": {"lat": 40.1000, "lng": -74.2000, "source": "manual"},
    "sunset": {"lat": 40.0900, "lng": -74.2100, "source": "osm"},
    "james": {"lat": 40.0920, "lng": -74.2120, "source": "osm"},
    "jackson": {"lat": 40.1000, "lng": -74.3500, "source": "osm"},
    "pine lake park": {"lat": 40.0300, "lng": -74.3000, "source": "manual"},
    "manchester": {"lat": 39.9800, "lng": -74.3300, "source": "osm"},
    "lutzk": {"lat": None, "lng": None, "source": "unresolved"},
    "oak vine": {"lat": 40.0950, "lng": -74.2200, "source": "manual"},
}


class Parts(unittest.TestCase):
    def test_splitting(self):
        self.assertEqual(geo.location_parts("Sunset / James Area"), ["sunset", "james"])
        self.assertEqual(geo.location_parts("Sunset & James"), ["sunset", "james"])
        self.assertEqual(geo.location_parts("Pine Lake Park, Manchester"), ["pine lake park", "manchester"])
        self.assertEqual(geo.location_parts("Lutzk near Westgate"), ["lutzk", "westgate"])
        self.assertEqual(geo.location_parts("Off Locust St"), ["locust st"])

    def test_normalising(self):
        self.assertEqual(geo.normalize("Oak & Vine"), "oak vine")
        self.assertEqual(geo.normalize("W. County Ln."), "w county ln")
        self.assertEqual(geo.normalize("Ridge Area"), "ridge")

    def test_aliases_resolve_like_the_real_name(self):
        self.assertEqual(geo.normalize("Jacksn"), "jackson")
        self.assertEqual(geo.normalize("Hearthstn"), "hearthstone")
        self.assertEqual(geo.normalize("Brookwd 1"), "brookwood 1")
        self.assertEqual(geo.location_parts("Hyson Area, Jacksn"), ["hyson", "jackson"])
        self.assertEqual(geo.location_parts("Bais Sholom"), ["bais shalom"])

    def test_duplicates_and_blanks(self):
        self.assertEqual(geo.location_parts("James / James"), ["james"])
        self.assertEqual(geo.location_parts(""), [])
        self.assertEqual(geo.location_parts(None), [])


class Resolve(unittest.TestCase):
    def test_single_place(self):
        r = geo.resolve("Raintree", PLACES)
        self.assertEqual((r["lat"], r["lng"], r["precision"]), (40.1, -74.2, "place"))

    def test_intersection_is_the_midpoint(self):
        r = geo.resolve("Sunset / James Area", PLACES)
        self.assertAlmostEqual(r["lat"], 40.091)
        self.assertAlmostEqual(r["lng"], -74.211)
        self.assertEqual(r["precision"], "place")

    def test_specific_place_beats_town(self):
        r = geo.resolve("Pine Lake Park, Manchester", PLACES)
        self.assertEqual((r["lat"], r["lng"]), (40.03, -74.3))   # not averaged with Manchester

    def test_town_only_is_marked_as_town(self):
        r = geo.resolve("Jackson", PLACES)
        self.assertEqual(r["precision"], "town")

    def test_whole_string_entry_wins(self):
        r = geo.resolve("Oak & Vine", PLACES)                   # "oak vine" is a manual whole-name entry
        self.assertEqual((r["lat"], r["lng"]), (40.095, -74.22))

    def test_intersection_matches_in_either_order(self):
        places = {"sunset james": {"lat": 40.08, "lng": -74.225, "source": "manual"}}
        for text in ("Sunset / James", "James / Sunset", "James & Sunset", "Sunset & James Area"):
            with self.subTest(text=text):
                self.assertEqual(geo.resolve(text, places)["lat"], 40.08)

    def test_unresolved_and_unknown_are_reported_differently(self):
        r = geo.resolve("Lutzk", PLACES)
        self.assertIsNone(r["lat"])
        self.assertEqual(r["unknown"], [])                        # known, just unresolved
        r = geo.resolve("Nowhereville", PLACES)
        self.assertEqual(r["unknown"], ["nowhereville"])

    def test_partially_known_location_uses_what_it_has(self):
        r = geo.resolve("Raintree / Nowhereville", PLACES)
        self.assertEqual((r["lat"], r["lng"]), (40.1, -74.2))
        self.assertEqual(r["unknown"], ["nowhereville"])

    def test_empty_location(self):
        self.assertIsNone(geo.resolve("", PLACES)["lat"])


class Expand(unittest.TestCase):
    def test_expansions(self):
        self.assertEqual(geo.expand_abbreviations("heritage pt"), "heritage point")
        self.assertEqual(geo.expand_abbreviations("mass"), "massachusetts avenue")
        self.assertEqual(geo.expand_abbreviations("negba st"), "negba street")
        self.assertEqual(geo.expand_abbreviations("w county ln"), "west county lane")
        self.assertEqual(geo.expand_abbreviations("hwl"), "howell")

    def test_ordinary_names_unchanged(self):
        self.assertEqual(geo.expand_abbreviations("raintree"), "raintree")
        self.assertEqual(geo.expand_abbreviations("sterling forest"), "sterling forest")


class Distance(unittest.TestCase):
    def test_haversine(self):
        self.assertEqual(geo.haversine_miles(40.1, -74.2, 40.1, -74.2), 0)
        d = geo.haversine_miles(*geo.LAKEWOOD, 39.9537, -74.1979)       # to Toms River
        self.assertTrue(9 < d < 12, d)

    def test_plausible_filters_far_matches(self):
        self.assertTrue(geo.plausible(40.0800, -74.2100))
        self.assertFalse(geo.plausible(40.7128, -74.0060))               # New York City


class ShippedPlaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.places = geo.load_places()

    def test_places_named_in_listings_are_in_the_right_town(self):
        """Regression: OSM once put Raintree/Wyndham in Freehold and Locust Grove near Asbury Park."""
        pl = self.places
        for key in ("raintree", "wyndham", "rockwell", "locust grove", "central", "chateau"):
            d = geo.haversine_miles(pl[key]["lat"], pl[key]["lng"], *geo.LAKEWOOD)
            self.assertLess(d, 5, key)
        self.assertGreater(pl["oak glen"]["lat"], 40.15)          # Howell, north of Lakewood

    def test_every_resolved_place_is_near_lakewood(self):
        far = [k for k, e in self.places.items()
               if e.get("lat") is not None and not geo.plausible(e["lat"], e["lng"])]
        self.assertEqual(far, [])

    def test_owner_confirmed_places(self):
        """Corrections supplied by the site owner must stay manual (never overwritten)."""
        for key in ("westgate", "sunset", "sunset james", "oak vine", "villas", "twin oaks",
                    "yeshiva", "the 70", "the 70 phase i", "the 70 phase ii", "brook hill",
                    "stamford meadows", "sterling place", "beaver crossings", "chateau park", "regency estates",
                    "clearsteam", "957 w county ln", "kol shimshon", "new england village", "bais shalom",
                    "club 21 jackson", "harmony hills jackson", "ridge", "heart of ridge", "ridge negba st", "brook ridge e 7th", "ridge bergen",
                    "belz shlav aleph", "belz shlav beis", "belz shlav gimel",
                    "prime jackson", "55+community", "fairways", "enclave", "chestnut", "chestnut gardens", "cross", "cross mass", "brook", "evergreen gardens"):
            with self.subTest(place=key):
                self.assertEqual(self.places[key]["source"], "manual")
                self.assertIsNotNone(self.places[key]["lat"])

    def test_owner_corrections_resolve_for_listing_text(self):
        for text, key in [("Westgate", "westgate"), ("Sunset / James Area", "sunset james"),
                          ("Sunset & James", "sunset james"), ("James & Sunset", "sunset james"),
                          ("Oak & Vine", "oak vine"), ("Villas", "villas"), ("Yeshiva Area", "yeshiva"),
                          ("The 70", "the 70"), ("Brook Hill", "brook hill"), ("Chestnut Area", "chestnut"), ("Stamford Meadows", "stamford meadows"), ("Bais Shalom Area", "bais shalom"), ("Heart of Ridge", "heart of ridge"), ("13th & Princeton", "13th princeton"), ("14th & Lexington", "14th lexington"),
                          ("5th & Lexington", "5th lexington"), ("7th & Princeton", "7th princeton"), ("E.7th & Nowlan", "e 7th nowlan"),
                          ("Central Area", "central"), ("Off Locust St.", "locust st"), ("Chateau Park", "chateau park"), ("Ridge / Negba St.", "ridge negba st"), ("Negba St. / Ridge", "ridge negba st"),
                          ("Brook / Ridge / E.7th", "brook ridge e 7th"), ("Ridge / Bergen", "ridge bergen"), ("Belz Shlav Aleph", "belz shlav aleph"), ("Prime Jackson Area", "prime jackson"), ("55+Community", "55+community"), ("Ridge Area", "ridge"),
                          ("957 W. County Ln.", "957 w county ln"), ("Club 21 Jackson", "club 21 jackson"), ("Chestnut Gardens", "chestnut gardens"), ("Off Chestnut", "chestnut"),
                          ("Cross & Mass.", "cross mass"), ("Mass. & Cross", "cross mass"), ("Evergreen Gardens", "evergreen gardens"), ("The 70 Phase II", "the 70 phase ii")]:
            with self.subTest(text=text):
                g = geo.resolve(text, self.places)
                self.assertEqual((g["lat"], g["lng"]), (self.places[key]["lat"], self.places[key]["lng"]))
                self.assertEqual(g["precision"], "place")

    def test_brook_hill_is_north_west_of_brook_and_county_line(self):
        e = self.places["brook hill"]
        self.assertGreater(e["lat"], 40.10523)      # north of the intersection
        self.assertLess(e["lng"], -74.18700)        # west of it
        self.assertLess(geo.haversine_miles(e["lat"], e["lng"], 40.10523, -74.18700), 0.6)

    def test_oak_and_vine_is_east_of_evergreen(self):
        e = self.places["oak vine"]
        self.assertGreater(e["lng"], -74.2182)     # east of Evergreen on Broadway
        self.assertLess(geo.haversine_miles(e["lat"], e["lng"], 40.0631, -74.2182), 1.0)

    def test_the_70_phases(self):
        p1, p2 = self.places["the 70 phase i"], self.places["the 70 phase ii"]
        self.assertEqual((p1["lat"], p1["lng"]),
                         (self.places["belz shlav aleph"]["lat"], self.places["belz shlav aleph"]["lng"]))
        # Phase II: south side of Route 70, between Vermont Ave and New Hampshire Ave
        self.assertTrue(-74.2094 < p2["lng"] < -74.1967)
        self.assertLess(p2["lat"], 40.0495)

    def test_ridge_bergen_is_between_the_two_streets(self):
        e = self.places["ridge bergen"]
        self.assertTrue(40.0920 < e["lat"] < 40.0979)

    def test_guessed_places_are_averages_of_the_named_places(self):
        pl = self.places
        f, e, c = pl["fairways"], pl["enclave"], pl["55+community"]
        self.assertAlmostEqual(c["lat"], (f["lat"] + e["lat"]) / 2, places=4)
        self.assertAlmostEqual(c["lng"], (f["lng"] + e["lng"]) / 2, places=4)
        names = ["brookwood 1", "brookwood 2", "brookwood 4", "harmony farms"]
        pj = pl["prime jackson"]
        self.assertAlmostEqual(pj["lat"], sum(pl[n]["lat"] for n in names) / 4, delta=0.0005)
        self.assertAlmostEqual(pj["lng"], sum(pl[n]["lng"] for n in names) / 4, delta=0.0005)

    def test_villas_is_on_twin_oaks(self):
        self.assertEqual((self.places["villas"]["lat"], self.places["villas"]["lng"]),
                         (self.places["twin oaks"]["lat"], self.places["twin oaks"]["lng"]))

    def test_generic_words_are_not_geocoded_on_their_own(self):
        self.assertNotIn("oak", self.places)
        self.assertNotIn("vine", self.places)

    def test_entries_are_well_formed(self):
        for k, e in self.places.items():
            with self.subTest(place=k):
                self.assertIn(e["source"], ("osm", "manual", "unresolved"))
                self.assertEqual(e["lat"] is None, e["lng"] is None)
                if e["source"] == "unresolved":
                    self.assertIsNone(e["lat"])


class PickerNames(unittest.TestCase):
    def name(self, raw, **extra):
        return geo.display_name("k", {"name": raw, **extra})

    def test_ordinal_streets(self):
        self.assertEqual(self.name("13Th"), "13th Street")
        self.assertEqual(self.name("14Th Street"), "14th Street")
        self.assertEqual(self.name("5Th"), "5th Street")
        self.assertEqual(self.name("E 7Th"), "E 7th Street")

    def test_street_suffixes(self):
        self.assertEqual(self.name("Cherry St"), "Cherry Street")
        self.assertEqual(self.name("Dewey Ave"), "Dewey Avenue")
        self.assertEqual(self.name("Cross St & Massachusetts Ave"), "Cross Street & Massachusetts Avenue")
        self.assertEqual(self.name("Rt 70"), "Route 70")

    def test_saints_and_small_words_untouched(self):
        self.assertEqual(self.name("St Katherine"), "St Katherine")
        self.assertEqual(self.name("Club At Jackson 21"), "Club at Jackson 21")

    def test_label_overrides_name(self):
        self.assertEqual(self.name("Brook Rd (at County Line Rd)", label="Brook Road"), "Brook Road")

    def test_duplicates_merge_and_manual_wins(self):
        places = {"14th": {"name": "14Th", "lat": 40.1, "lng": -74.2, "source": "osm"},
                  "14th street": {"name": "14Th Street", "lat": 40.1, "lng": -74.2, "source": "manual"},
                  "james": {"name": "James", "lat": 40.0790, "lng": -74.2369, "source": "osm"},
                  "james street": {"name": "James Street", "lat": 40.0790, "lng": -74.2369, "source": "osm"},
                  "central": {"name": "Central", "lat": 40.094, "lng": -74.253, "source": "osm"},
                  "central avenue": {"name": "Central Avenue", "lat": 40.089, "lng": -74.230, "source": "osm"}}
        names = [p["name"] for p in geo.picker_entries(places)]
        self.assertEqual(names.count("14th Street"), 1)
        self.assertNotIn("James", names)
        self.assertIn("James Street", names)
        # far-apart twins are NOT merged: they may be different places
        self.assertIn("Central", names)
        self.assertIn("Central Avenue", names)


class ShippedPicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.picker = geo.picker_entries(geo.load_places())
        cls.names = [p["name"] for p in cls.picker]

    def test_names_are_unique(self):
        low = [n.lower() for n in self.names]
        self.assertEqual(len(low), len(set(low)))

    def test_numbered_streets_are_spelled_out(self):
        for n in ("5th Street", "7th Street", "13th Street", "14th Street"):
            self.assertEqual(self.names.count(n), 1, n)
        for n in self.names:
            self.assertNotRegex(n, r"\d(St|Nd|Rd|Th)\b")           # "13Th"
            self.assertNotRegex(n, r"^\d+(st|nd|rd|th)$")            # bare "14th"

    def test_no_abbreviations_or_internal_notes(self):
        for n in self.names:
            self.assertNotRegex(n, r"\b(St|Ave|Rd|Ln|Ct|Dr|Blvd)\.?$", n)
            self.assertNotRegex(n, r"^R(?:t|te)\b", n)
            self.assertNotIn("avg of", n.lower())
            self.assertNotIn("middle", n.lower())

    def test_seventh_and_east_seventh_are_different_streets(self):
        pts = {p["name"]: (p["lat"], p["lng"]) for p in self.picker}
        self.assertIn("7th Street", pts)
        self.assertIn("E 7th Street", pts)
        self.assertNotEqual(pts["7th Street"], pts["E 7th Street"])
        self.assertLess(pts["7th Street"][1], pts["E 7th Street"][1])      # 7th is west of E 7th

    def test_same_street_spellings_are_one_entry(self):
        for name, bare in (("Central Avenue", "Central"), ("Locust Street", "Locust"), ("Park Avenue", "Park"),
                           ("Somerset Avenue", "Somerset"), ("Chateau Park", "Chateau")):
            self.assertEqual(self.names.count(name), 1, name)
            self.assertNotIn(bare, self.names)

    def test_central_is_where_central_meets_new_central(self):
        pts = {p["name"]: (p["lat"], p["lng"]) for p in self.picker}
        self.assertLess(geo.haversine_miles(*pts["Central Avenue"], 40.0905, -74.2377), 0.1)

    def test_routes_point_at_different_places(self):
        pts = {p["name"]: (p["lat"], p["lng"]) for p in self.picker}
        self.assertEqual(len({pts["Route 9"], pts["Route 70"], pts["Route 88"]}), 3)

    def test_every_entry_has_coordinates_near_lakewood(self):
        for p in self.picker:
            self.assertTrue(geo.plausible(p["lat"], p["lng"]), p["name"])


class AuditedPlaces(unittest.TestCase):
    def test_resolve_flags_unchecked_osm_pins(self):
        places = {"raintree": {"lat": 40.1, "lng": -74.2, "source": "osm"},
                  "sunset": {"lat": 40.09, "lng": -74.21, "source": "manual"},
                  "jackson": {"lat": 40.1, "lng": -74.35, "source": "osm"}}
        self.assertEqual(geo.resolve("Raintree", places)["unverified"], ["raintree"])
        self.assertEqual(geo.resolve("Sunset", places)["unverified"], [])
        self.assertEqual(geo.resolve("Jackson", places)["unverified"], [])      # town-level is fine
        self.assertEqual(geo.resolve("Sunset / Raintree", places)["unverified"], ["raintree"])

    def test_checks_warns_about_unverified_pins_but_never_blocks(self):
        rows = [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3],
                 "location": "Raintree", "phones": ["732-555-0101"], "comments": "x", "rent": 2000,
                 "lat": 40.1, "lng": -74.2, "geo_unknown": [], "geo_unverified": ["raintree"]} for i in range(100)]
        errors, warnings = checks.check(rows)
        self.assertEqual(errors, [])
        self.assertTrue(any("never checked on Google Maps" in w and "raintree" in w for w in warnings))

    def test_audited_places_regressions(self):
        """Places the Google Maps audit moved: OSM had them in the wrong town."""
        pl = geo.load_places()
        self.assertLess(pl["jackson 21"]["lng"], -74.34)             # west Jackson, not Lakewood's edge
        self.assertGreater(pl["topaz"]["lat"], 40.15)                # Topaz Dr is in north Jackson
        self.assertLess(pl["meadow run"]["lng"], -74.27)             # Meadow Run Ct is in west Jackson
        self.assertGreater(pl["ramtown"]["lat"], 40.115)
        for k in ("jackson 21", "topaz", "meadow run", "ramtown", "hope", "spruce st", "squankum",
                  "clifton", "ocean avenue", "pine river", "new prospect jackson"):
            self.assertEqual(pl[k]["source"], "manual", k)


class GeoChecks(unittest.TestCase):
    def listings(self, n, placed):
        return [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3],
                 "location": f"Raintree {i}", "phones": ["732-555-0101"], "comments": "x", "rent": 2000,
                 "lat": 40.1 if i < placed else None, "lng": -74.2 if i < placed else None,
                 "geo_unknown": [] if i < placed else [f"raintree {i}"]} for i in range(n)]

    def test_fully_placed_is_clean(self):
        self.assertEqual(checks.check(self.listings(100, 100)), ([], []))

    def test_unknown_names_warn_but_never_block(self):
        errors, warnings = checks.check(self.listings(100, 60))
        self.assertEqual(errors, [])
        self.assertTrue(any("map" in w for w in warnings))
        self.assertTrue(any("40 place name(s)" in w and "raintree 60" in w for w in warnings))

    def test_listings_without_geo_fields_are_not_penalised(self):
        rows = [{k: v for k, v in x.items() if k not in ("lat", "lng", "geo_unknown")}
                for x in self.listings(100, 100)]
        self.assertEqual(checks.check(rows), ([], []))


if __name__ == "__main__":
    unittest.main()
