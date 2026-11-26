"""Tests for location -> coordinates (geo.py) and its use in the build.

Run:  python3 -m unittest discover -s tests -v
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: E402
import geo  # noqa: E402
import towns  # noqa: E402

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


class Addresses(unittest.TestCase):
    def test_addresses_are_recognised(self):
        for a in ("957 W. County Ln.", "22 Enclave Blvd.", "415 Laurel Ave.", "12 Brook St", "957 W County Line Road"):
            self.assertTrue(geo.looks_like_address(a), a)

    def test_neighbourhoods_are_not_addresses(self):
        for n in ("13th & Princeton", "5th & Lexington", "7th Street", "14th Street Area", "55+Community",
                  "55+ Communities (Fairways / Enclave)", "Brookwood 1", "Jackson 21", "The 70", "The 70 Phase II",
                  "Club at Jackson 21", "Route 88", "E.7th & Nowlan", "", None):
            self.assertFalse(geo.looks_like_address(n), n)

    def test_confirmed_address_sits_on_its_neighbourhood(self):
        """Owner-confirmed: each address uses the coordinates of the neighbourhood it lies in."""
        pl = geo.load_places()
        for key, hood in (("22 enclave blvd", "enclave"), ("957 w county ln", "w kennedy"),
                          ("415 laurel ave", "route 88 clover")):
            self.assertTrue(geo.looks_like_address(key), key)
            self.assertEqual(pl[key]["neighborhood"], hood)
            self.assertEqual((pl[key]["lat"], pl[key]["lng"]), (pl[hood]["lat"], pl[hood]["lng"]), key)
            self.assertEqual(pl[key]["source"], "manual")

    def test_resolved_address_listings_use_the_neighbourhood_point(self):
        pl = geo.load_places()
        for text, hood in (("22 Enclave Blvd.", "enclave"), ("957 W. County Ln.", "w kennedy"), ("415 Laurel Ave.", "route 88 clover")):
            g = geo.resolve(text, pl)
            self.assertEqual((g["lat"], g["lng"]), (pl[hood]["lat"], pl[hood]["lng"]), text)

    def test_checks_stays_quiet_once_the_neighbourhood_is_confirmed(self):
        rows = [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3],
                 "location": "957 W. County Ln." if i == 0 else f"Raintree {i}", "phones": ["732-555-0101"],
                 "comments": "x", "rent": 2000, "lat": 40.1, "lng": -74.2, "geo_unknown": [],
                 "geo_neighborhood": "w kennedy" if i == 0 else None} for i in range(100)]
        self.assertFalse(any("street addresses" in w for w in checks.check(rows)[1]))

    def test_picker_never_offers_an_address(self):
        places = {"957 w county ln": {"name": "957 W County Line Rd", "lat": 40.1, "lng": -74.2, "source": "manual"},
                  "raintree": {"name": "Raintree", "lat": 40.09, "lng": -74.16, "source": "manual"}}
        self.assertEqual([p["name"] for p in geo.picker_entries(places)], ["Raintree"])

    def test_checks_flags_address_locations_without_blocking(self):
        rows = [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3],
                 "location": "957 W. County Ln." if i == 0 else f"Raintree {i}", "phones": ["732-555-0101"],
                 "comments": "x", "rent": 2000, "lat": 40.1, "lng": -74.2, "geo_unknown": []} for i in range(100)]
        errors, warnings = checks.check(rows)
        self.assertEqual(errors, [])
        self.assertTrue(any("street addresses" in w and "957 W. County Ln." in w for w in warnings))
        clean = [dict(x, location=f"Raintree {i}") for i, x in enumerate(rows)]
        self.assertFalse(any("street addresses" in w for w in checks.check(clean)[1]))


class OneNeighbourhoodOneEntry(unittest.TestCase):
    """Regression: 'Clover' and 'Route 88 & Clover' were listed as two neighbourhoods (and the Clover pin was
    0.4 mi off, so Arlington outranked the Clover listing)."""

    def test_intersection_on_top_of_its_street_is_folded_in(self):
        places = {"clover": {"name": "Clover", "lat": 40.0907, "lng": -74.2003, "source": "manual"},
                  "route 88 clover": {"name": "Route 88 & Clover", "lat": 40.0907, "lng": -74.2003, "source": "manual"},
                  "13th": {"name": "13th Street", "lat": 40.1041, "lng": -74.2103, "source": "manual"},
                  "13th princeton": {"name": "13th Street & Princeton Avenue", "lat": 40.1041, "lng": -74.2103, "source": "manual"},
                  "cross": {"name": "Cross Street", "lat": 40.0663, "lng": -74.2380, "source": "manual"},
                  "cross mass": {"name": "Cross Street & Massachusetts Avenue", "lat": 40.0603, "lng": -74.2294, "source": "manual"}}
        names = [p["name"] for p in geo.picker_entries(places)]
        self.assertEqual(names, ["13th Street", "Clover", "Cross Street", "Cross Street & Massachusetts Avenue"])

    def test_street_suffix_variants_count_as_the_same_name(self):
        places = {"clover": {"name": "Clover", "lat": 40.09, "lng": -74.2, "source": "manual"},
                  "x": {"name": "Ocean Avenue (Route 88) & Clover Street", "lat": 40.09, "lng": -74.2, "source": "manual"}}
        self.assertEqual([p["name"] for p in geo.picker_entries(places)], ["Clover"])

    def test_resolve_reports_how_far_apart_an_averaged_pin_is(self):
        places = {"a": {"lat": 40.00, "lng": -74.20, "source": "manual"}, "b": {"lat": 40.00, "lng": -74.30, "source": "manual"}}
        self.assertGreater(geo.resolve("A / B", places)["spread"], 5)
        self.assertEqual(geo.resolve("A", places)["spread"], 0)

    def test_checks_warns_when_a_pin_averages_distant_places(self):
        rows = [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3],
                 "location": "A / B" if i == 0 else f"Raintree {i}", "phones": ["732-555-0101"], "comments": "x",
                 "rent": 2000, "lat": 40.1, "lng": -74.2, "geo_unknown": [], "geo_spread": 7.0 if i == 0 else 0}
                for i in range(100)]
        errors, warnings = checks.check(rows)
        self.assertEqual(errors, [])
        self.assertTrue(any("2 miles apart" in w and "A / B" in w for w in warnings))


class PickerTowns(unittest.TestCase):
    """Owner (2026-11-22): every place shows its town, like the streets do; Harfield is Jackson, and the
    neighbourhoods Harmony Farms / Harmony Hills just say Jackson."""

    def test_town_comes_from_the_pin(self):
        places = {"harfield": {"name": "Harfield", "lat": 40.143, "lng": -74.270, "source": "manual"},
                  "raintree": {"name": "Raintree", "lat": 40.0968, "lng": -74.1646, "source": "manual"}}
        by = {p["name"]: p.get("town") for p in geo.picker_entries(places)}
        self.assertEqual(by, {"Harfield": "Jackson", "Raintree": "Lakewood"})

    def test_a_trailing_town_in_the_name_moves_to_the_town_field(self):
        places = {"hh": {"name": "Harmony Hills, Jackson", "lat": 40.1656, "lng": -74.3056, "source": "manual"},
                  "mk": {"name": "Mackenzie Toms River", "lat": 40.0325, "lng": -74.2437, "source": "manual"}}
        by = {p["name"]: p["town"] for p in geo.picker_entries(places)}
        self.assertEqual(by, {"Harmony Hills": "Jackson", "Mackenzie": "Toms River"})

    def test_only_the_places_own_town_is_stripped(self):
        self.assertEqual(geo.strip_town("Club at Jackson 21", "Jackson"), "Club at Jackson 21")
        self.assertEqual(geo.strip_town("Jackson", "Jackson"), "Jackson")                  # nothing would be left
        self.assertEqual(geo.strip_town("Pine Lake Park, Manchester", "Lakewood"), "Pine Lake Park, Manchester")
        self.assertEqual(geo.strip_town("Pine Lake Park, Manchester", "Manchester"), "Pine Lake Park")

    def test_a_town_has_no_town(self):
        places = {"jackson": {"name": "Jackson", "lat": 40.1, "lng": -74.35, "source": "osm"}}
        self.assertNotIn("town", geo.picker_entries(places)[0])

    def test_same_name_in_two_towns_stays_two_entries(self):
        places = {"a": {"name": "Pine Street", "lat": 40.074, "lng": -74.2033, "source": "manual"},
                  "b": {"name": "Pine Street", "lat": 40.12, "lng": -74.35, "source": "manual"}}
        self.assertEqual(sorted(p["town"] for p in geo.picker_entries(places)), ["Jackson", "Lakewood"])


class NotNeighbourhoods(unittest.TestCase):
    """Owner (2026-11-22): 'Prime Jackson Area' is not a neighbourhood. Vague listing phrases may get a guessed pin
    (so the listing still sorts by distance) but are never offered as places in the Near suggestions."""

    def test_hidden_entries_keep_their_pin_but_are_not_offered(self):
        places = {"prime jackson": {"name": "Prime Jackson Area", "lat": 40.119, "lng": -74.249, "source": "manual", "hide": True},
                  "raintree": {"name": "Raintree", "lat": 40.0968, "lng": -74.1646, "source": "manual"}}
        self.assertEqual([p["name"] for p in geo.picker_entries(places)], ["Raintree"])
        self.assertEqual(geo.resolve("Prime Jackson Area", places)["lat"], 40.119)      # the listing still has a pin

    def test_the_shipped_vague_phrases_are_hidden_but_still_placed(self):
        places = geo.load_places()
        names = [p["name"] for p in geo.picker_entries(places)]
        for key, shown in (("prime jackson", "Prime Jackson Area"), ("55+community", "55+ Communities (Fairways / Enclave)")):
            self.assertTrue(places[key].get("hide"), key)
            self.assertNotIn(shown, names)
            self.assertIsNotNone(places[key]["lat"])                                   # listings keep their pin
        self.assertIn("Enclave at the Fairways (55+)", names)                          # the real neighbourhoods stay
        self.assertIn("The Fairways at Lake Ridge (55+)", names)

    def test_no_picker_name_is_a_vague_area(self):
        for p in geo.picker_entries(geo.load_places()):
            self.assertFalse(p["name"].lower().endswith(" area"), p["name"])
            self.assertNotIn("communities", p["name"].lower().replace("55+ communities", ""))


class ShippedPickerTowns(unittest.TestCase):
    def test_every_neighbourhood_has_a_town_and_the_known_ones_are_right(self):
        pk = geo.picker_entries(geo.load_places())
        by = {p["name"]: p.get("town") for p in pk}
        for p in pk:
            if p["name"].lower() in geo.TOWN_NAMES:
                self.assertNotIn("town", p, p["name"])
            else:
                self.assertIn(p["town"], towns.TOWN_CENTERS, p["name"])
        for name, town in (("Harfield", "Jackson"), ("Harmony Farms", "Jackson"), ("Harmony Hills", "Jackson"),
                           ("Raintree", "Lakewood"), ("Pine Lake Park", "Manchester"), ("Ramtown", "Howell"),
                           ("Whitewater Court", "Toms River"), ("Brookwood 1", "Jackson"), ("Westgate", "Lakewood")):
            self.assertEqual(by[name], town, name)


class ShippedPicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.picker = geo.picker_entries(geo.load_places())
        cls.names = [p["name"] for p in cls.picker]

    def test_clover_is_one_neighbourhood_at_the_88_corner(self):
        clover = [p for p in self.picker if "clover" in p["name"].lower()]
        self.assertEqual([p["name"] for p in clover], ["Clover"])
        self.assertLess(geo.haversine_miles(clover[0]["lat"], clover[0]["lng"], 40.09076, -74.20032), 0.02)

    def test_no_intersection_duplicates_a_neighbourhood_it_sits_on(self):
        for p in self.picker:
            parts = [geo._base(x) for x in __import__("re").split(r"\s+[&/]\s+", p["name"])]
            if len(parts) < 2:
                continue
            for q in self.picker:
                if q is not p and geo._base(q["name"]) in parts:
                    self.assertGreater(geo.haversine_miles(p["lat"], p["lng"], q["lat"], q["lng"]), 0.25,
                                       (p["name"], q["name"]))

    def test_picking_clover_ranks_the_clover_listing_first(self):
        import json
        pin = next(p for p in self.picker if p["name"] == "Clover")
        L = [x for x in json.loads((ROOT / "listings.json").read_text())["listings"] if x.get("lat")]
        nearest = min(L, key=lambda x: geo.haversine_miles(pin["lat"], pin["lng"], x["lat"], x["lng"]))
        self.assertIn("clover", nearest["location"].lower())

    def test_no_address_in_the_picker(self):
        self.assertEqual([n for n in self.names if geo.looks_like_address(n)], [])

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
        # Locust is not here any more: the owner (2026-11-26) wants it listed as the neighbourhood "Locust" (like "Chestnut")
        for name, bare in (("Central Avenue", "Central"), ("Park Avenue", "Park"),
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


class Lutzk(unittest.TestCase):
    """Owner: add Lutsk/Lutzk as a neighbourhood: Bais Medrash Lutzk on East Veterans (Google Maps: 520 New Egypt Rd)."""

    @classmethod
    def setUpClass(cls):
        cls.places = geo.load_places()
        cls.picker = geo.picker_entries(cls.places)

    def test_lutzk_is_a_manual_neighbourhood_in_lakewood(self):
        e = self.places["lutzk"]
        self.assertEqual(e["source"], "manual")
        self.assertLess(geo.haversine_miles(e["lat"], e["lng"], 40.08419, -74.25470), 0.05)

    def test_it_is_in_the_picker_and_findable_as_lutsk(self):
        entry = next(p for p in self.picker if p["name"] == "Lutzk")
        self.assertEqual(entry.get("aka"), ["Lutsk"])

    def test_either_spelling_in_a_listing_resolves(self):
        for text in ("Lutzk", "Lutsk", "Lutzk Area"):
            self.assertEqual(geo.resolve(text, self.places)["lat"], self.places["lutzk"]["lat"], text)

    def test_x_near_y_is_at_x(self):
        g = geo.resolve("Lutzk near Westgate", self.places)
        self.assertEqual((g["lat"], g["lng"]), (self.places["lutzk"]["lat"], self.places["lutzk"]["lng"]))

    def test_near_with_an_unknown_first_part_still_uses_what_it_can(self):
        places = {"westgate": {"lat": 40.087, "lng": -74.255, "source": "manual"}}
        g = geo.resolve("Nowhereville near Westgate", places)
        self.assertEqual(g["lat"], 40.087)


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


class ShulTests(unittest.TestCase):
    def test_shuls_file_loads_lakewood_first_with_towns(self):
        shuls = geo.load_shuls()
        self.assertGreater(len(shuls), 150)
        self.assertEqual(shuls[0]["town"], "Lakewood")
        for s in shuls:
            self.assertTrue(geo.plausible(s["lat"], s["lng"]), s["name"])
            self.assertTrue(s["town"], s["name"])
        names = {s["name"] for s in shuls}
        self.assertTrue(any("Spruce Street Shul" == n for n in names))

    def test_hidden_shul_is_dropped(self):
        import json, tempfile, pathlib
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "s.json"
            f.write_text(json.dumps({"shuls": [{"name": "A", "lat": 40.09, "lng": -74.21, "town": "Lakewood"},
                                               {"name": "B", "lat": 40.09, "lng": -74.21, "hide": True}]}))
            self.assertEqual([s["name"] for s in geo.load_shuls(f)], ["A"])


class ShulNameAndMergeTests(unittest.TestCase):
    def test_nobody_says_congregation(self):
        for raw, want in [("Congregation Kol Aryeh", "Kol Aryeh"), ("Cong. Belz Meadows", "Belz Meadows"),
                          ("Congregation of North Albert", "North Albert"),
                          ("Lakewood Sephardic Congregation", "Lakewood Sephardic"),
                          ("Cong Berditchev / Berditchev Kloiz", "Berditchev / Berditchev Kloiz")]:
            self.assertEqual(geo.spoken_shul_name(raw), want)
        for s in geo.load_shuls():
            self.assertNotRegex(s["name"], r"(?i)\bcong")

    def test_shul_that_is_also_a_neighborhood_is_listed_once(self):
        picker = geo.picker_entries(geo.load_places())
        shuls, merged = geo.merge_shuls(geo.load_shuls(), picker)
        names = {s["name"] for s in shuls}
        self.assertNotIn("Kol Shimshon", names)           # the neighbourhood Kol Shimshon covers it
        self.assertNotIn("Bais Medrash Lutzk", names)
        kol = [p for p in merged if p["name"] == "Kol Shimshon"]
        self.assertEqual(len(kol), 1)
        self.assertTrue(kol[0]["shul"])
        lutzk = [p for p in merged if p["name"] == "Lutzk"][0]
        self.assertIn("Bais Medrash Lutzk", lutzk["aka"])
        self.assertIn("Kol Aryeh", names)                  # a shul only: stays a shul

    def test_a_street_is_not_merged_with_a_shul_named_after_it(self):
        picker = [{"name": "Spruce Street", "lat": 40.0, "lng": -74.2, "town": "Lakewood"}]
        shuls = [{"name": "Spruce Street Shul", "lat": 40.0, "lng": -74.2, "town": "Lakewood", "address": "", "aka": []}]
        keep, merged = geo.merge_shuls(shuls, picker)
        self.assertEqual(len(keep), 1)
        self.assertFalse(merged[0].get("shul"))

    def test_bmg_alone_is_the_campus_between_6th_and_7th_and_the_other_buildings_have_their_own_names(self):
        picker = geo.picker_entries(geo.load_places())
        shuls, merged = geo.merge_shuls(geo.load_shuls(), picker)
        names = [s["name"] for s in shuls]
        # owner 2026-11-24: "BMG" = the main campus (6th and 7th St), one place
        bmg = [p for p in merged if p["name"] == "BMG"]
        self.assertEqual(len(bmg), 1)
        self.assertTrue(bmg[0]["shul"])
        self.assertTrue(40.0955 < bmg[0]["lat"] < 40.0970 and -74.2225 < bmg[0]["lng"] < -74.2210)   # between 6th and 7th St
        self.assertFalse(any(n.startswith("BMG - Main") or n.startswith("BMG - Herzka") for n in names))   # merged into BMG
        # the other buildings go by their own names, and all of them come up for "yeshiva"
        for own in ("Beis Aharon", "Forest Beis Medrash"):
            self.assertIn(own, names)
        bs = [p for p in merged if p["name"] == "Beis Shalom"]
        self.assertEqual(len(bs), 1)
        every = {p["name"]: p.get("aka", []) for p in merged}
        every.update({s["name"]: s.get("aka", []) for s in shuls})
        for who in ("BMG", "Beis Shalom", "Beis Aharon", "Forest Beis Medrash"):
            self.assertIn("Yeshiva", every[who], who)


class OwnerSearchRules(unittest.TestCase):
    def test_preferred_streets_point_at_real_lakewood_streets(self):
        pref = geo.load_preferred_streets()
        self.assertEqual(pref["forest"], "Forest Avenue")
        self.assertEqual(pref["birch"], "Birch Street")
        import json
        names = {(s[0], ) for s in json.loads((ROOT / "streets.json").read_text())["streets"]}
        for street in pref.values():
            self.assertIn((street,), names)

    def test_princeton_beis_medrash_is_at_princeton_and_7th(self):
        s = [x for x in geo.load_shuls() if x["name"] == "Princeton Beis Medrash"]
        self.assertEqual(len(s), 1)
        self.assertLess(geo.haversine_miles(s[0]["lat"], s[0]["lng"], 40.0976568, -74.2082505), 0.02)   # Google Maps: BMG Bais Shmuel, Princeton Ave & 7th St
        self.assertIn("BMG Bais Shmuel", s[0]["aka"])
        self.assertEqual(s[0]["town"], "Lakewood")
        self.assertIn("Yeshiva of Princeton", s[0]["aka"])


class TownCentres(unittest.TestCase):
    """Owner 2026-11-24: "Jackson" or "Toms River" alone = the Jewish area there (average of the places named), not the township centre."""

    def test_jackson_alone_is_the_average_of_the_jackson_places_not_the_township_centre(self):
        places = geo.load_places()
        jackson_places = [e for k, e in places.items() if e.get("lat") is not None and not e.get("hide") and k not in geo.TOWNS
                          and towns.town_of(e["lat"], e["lng"]) == "Jackson"]
        self.assertGreaterEqual(len(jackson_places), 3)
        centers = geo.town_centers([], places)             # no listings: falls back to the named places
        c = centers["Jackson"]
        self.assertAlmostEqual(c["lat"], sum(e["lat"] for e in jackson_places) / len(jackson_places), places=4)
        township_centre = places["jackson"]
        # the township centre is out west; the Jewish area is much closer to Lakewood
        self.assertLess(geo.haversine_miles(c["lat"], c["lng"], *geo.LAKEWOOD), geo.haversine_miles(township_centre["lat"], township_centre["lng"], *geo.LAKEWOOD) - 2)
        self.assertEqual(towns.town_of(c["lat"], c["lng"]), "Jackson")

    def test_listings_naming_places_in_a_town_set_its_middle(self):
        places = geo.load_places()
        listings = [{"geo": "place", "lat": 40.13, "lng": -74.30, "geo_spread": 0}, {"geo": "place", "lat": 40.14, "lng": -74.28, "geo_spread": 0},
                    {"geo": "place", "lat": 40.12, "lng": -74.29, "geo_spread": 0}]
        c = geo.town_centers(listings, places)["Jackson"]
        self.assertAlmostEqual(c["lat"], 40.13, places=3)
        self.assertEqual(c["n"], 3)

    def test_apply_moves_only_town_level_listings(self):
        centers = {"Jackson": {"lat": 40.127, "lng": -74.29, "area_miles": 2.5, "n": 5}}
        town_pin = geo.load_places()["jackson"]
        a = {"geo": "town", "location": "Jackson", "lat": town_pin["lat"], "lng": town_pin["lng"]}
        b = {"geo": "place", "location": "Harmony Hills", "lat": 40.13, "lng": -74.28}
        geo.apply_town_centers([a, b], centers)
        self.assertEqual((a["lat"], a["lng"]), (40.127, -74.29))
        self.assertEqual(a["geo_area_miles"], 2.5)
        self.assertEqual((b["lat"], b["lng"]), (40.13, -74.28))


class HeritagePoint(unittest.TestCase):
    def test_howell_heritage_listings_are_pinned_at_heritage_point_not_the_town_centre(self):
        places = geo.load_places()
        e = places["heritage pt"]
        self.assertEqual(e["source"], "manual")
        self.assertTrue(geo.plausible(e["lat"], e["lng"]))
        self.assertLess(geo.haversine_miles(e["lat"], e["lng"], 40.1452302, -74.2338826), 0.05)   # Google Maps: Heritage Dr, Howell 07731
        for loc in ("Howell / Heritage Pt.", "Heritage Pt. / Howell"):
            g = geo.resolve(loc, places)
            self.assertEqual(g["precision"], "place", loc)
            self.assertAlmostEqual(g["lat"], e["lat"], places=4)


class NeighborhoodHistory(unittest.TestCase):
    """The 'Neighborhoods' index/browse list must never lose a name just because one week's PDF
    happens to have no listing there (owner, 2026-11-26)."""

    def test_display_name_takes_the_first_part_and_drops_a_trailing_area(self):
        self.assertEqual(geo.neighborhood_display_name("Ridge Area"), "Ridge")
        self.assertEqual(geo.neighborhood_display_name("Sunset / James Area"), "Sunset")
        self.assertEqual(geo.neighborhood_display_name("Holly Oaks, Manchester"), "Holly Oaks")
        self.assertEqual(geo.neighborhood_display_name("Club at Jackson 21"), "Club at Jackson 21")
        self.assertEqual(geo.neighborhood_display_name(""), "")
        self.assertEqual(geo.neighborhood_display_name(None), "")

    def test_counts_include_zero_for_a_seen_name_missing_this_week(self):
        listings = [{"location": "Raintree"}, {"location": "Raintree Area"}, {"location": "Westgate"}]
        counts = geo.neighborhood_counts(listings, seen=["Raintree", "Lakewood Commons"])
        self.assertEqual(counts, {"Raintree": 2, "Westgate": 1, "Lakewood Commons": 0})

    def test_load_neighborhoods_seen_tolerates_a_missing_file(self):
        self.assertEqual(geo.load_neighborhoods_seen("/no/such/file.json"), [])

    def test_load_with_no_path_follows_a_patched_module_attribute(self):
        """build.py calls load_neighborhoods_seen() with no argument, so a test that redirects
        the real file away (e.g. BuildGate in test_checks.py, with fixture data) must do it by
        patching geo.NEIGHBORHOODS_SEEN_FILE, and that patch must actually take effect - not get
        ignored because the real path was already captured as a default argument."""
        tmp = pathlib.Path(tempfile.mkdtemp()) / "seen.json"
        tmp.write_text(json.dumps(["Fixture Only"]))
        with mock.patch.object(geo, "NEIGHBORHOODS_SEEN_FILE", tmp):
            self.assertEqual(geo.load_neighborhoods_seen(), ["Fixture Only"])

    def test_shipped_history_is_a_superset_of_a_past_weeks_names(self):
        # these were seen in a real build and must stay discoverable even on a week without one
        seen = set(geo.load_neighborhoods_seen())
        for name in ("Lakewood Commons", "Westgate", "Club at Jackson 21"):
            with self.subTest(name=name):
                self.assertIn(name, seen)


class NamesAddedNov26(unittest.TestCase):
    """Names from the Nov. 25, 2026 list, each looked up on Google Maps."""

    def test_each_location_is_on_the_map(self):
        places = geo.load_places()
        for location in ["Outside Brookwd 1", "Heritage Pt. / Howl.", "10th St. / Yeshiva", "Prospect Heights",
                         "Manetta / Ridge", "Tamarind Park", "Yesodei Court", "Glen Ave.", "Harvard Street", "12th & Princeton",
                         "Laurel / Rt.88", "Squankum / Harvard", "Cov.:Princeton", "Forest Park", "Wyndham 2",
                         "Daniel Drive", "Blue River"]:
            r = geo.resolve(location, places)
            self.assertEqual(r["unknown"], [], location)
            self.assertTrue(r["lat"] and geo.plausible(r["lat"], r["lng"]), location)

    def test_same_street_same_point(self):
        places = geo.load_places()
        for a, b in [("harvard", "harvard street"), ("glen ave", "glen avenue"), ("wyndham 2", "wyndham")]:
            self.assertEqual((places[a]["lat"], places[a]["lng"]), (places[b]["lat"], places[b]["lng"]), a)

    def test_outside_and_howl_are_understood(self):
        self.assertEqual(geo.location_parts("Outside Brookwd 1"), ["brookwood 1"])
        self.assertEqual(geo.location_parts("Heritage Pt. / Howl."), ["heritage pt", "howell"])


class OwnerNeighborhoodsNov26(unittest.TestCase):
    """Owner, 2026-11-26."""

    def setUp(self):
        self.places = geo.load_places()
        self.picker = {p["name"]: p for p in geo.picker_entries(self.places)}

    def test_chestnut_and_locust_are_their_own_neighborhoods(self):
        for name in ("Chestnut", "Locust", "Chestnut Acres", "Locust Grove"):
            self.assertIn(name, self.picker)
        self.assertNotIn("Locust Street", self.picker)
        for location, name in [("Off Chestnut", "chestnut"), ("Chestnut Area", "chestnut"), ("Off Locust St.", "locust")]:
            r = geo.resolve(location, self.places)
            self.assertEqual((r["lat"], r["lng"]), (self.places[name]["lat"], self.places[name]["lng"]), location)

    def test_club_at_jackson_21_is_jackson_21(self):
        self.assertIn("Club at Jackson 21", self.picker["Jackson 21"]["aka"])
        self.assertFalse([n for n in self.picker if "Club" in n and "21" in n])

    def test_oak_meadows_and_the_vineyards_are_on_the_map(self):
        for location, town in [("Oak Meadows", "Lakewood"), ("The Vineyards", "Jackson")]:
            r = geo.resolve(location, self.places)
            self.assertTrue(r["lat"], location)
            self.assertEqual(self.picker[location]["town"], town)

    def test_near_chateau_is_chateau_park(self):
        r = geo.resolve("Near Chateau", self.places)
        self.assertEqual((r["lat"], r["lng"]), (self.places["chateau park"]["lat"], self.places["chateau park"]["lng"]))


class SharedAreas(unittest.TestCase):
    """Owner, 2026-11-26: Albert Run and Sims are one area (also searched with Albert), listed as two neighbourhoods."""

    def test_a_listing_there_belongs_to_both_and_to_albert(self):
        also = geo.load_neighborhood_also()
        for location in ("Albert Run / Sims", "Albert Run", "Sims"):
            self.assertEqual(sorted(geo.listing_areas(location, also)), ["Albert", "Albert Run", "Sims"], location)

    def test_an_albert_listing_stays_in_albert_only(self):
        also = geo.load_neighborhood_also()
        self.assertEqual(geo.listing_areas("Albert Area", also), [])
        self.assertEqual(geo.listing_areas("Raintree", also), [])

    def test_both_are_neighborhoods_on_the_map(self):
        places = geo.load_places()
        picker = {p["name"] for p in geo.picker_entries(places)}
        self.assertTrue({"Albert", "Albert Run", "Sims"} <= picker)
        a, s = places["albert run"], places["sims"]
        self.assertLess(geo.haversine_miles(a["lat"], a["lng"], s["lat"], s["lng"]), 0.05)


class DescriptionWordsAreNotNeighbourhoods(unittest.TestCase):
    def test_all_capital_fragments_are_not_kept_as_names(self):
        self.assertTrue(geo.looks_like_description("KITCHENETTE. PRIVATE"))
        for real in ("BMG", "Brookwood 1", "The 70", "Rt.9 & Cross", "KOL ARY"):
            self.assertFalse(geo.looks_like_description(real), real)
        counts = geo.neighborhood_counts([{"location": "Raintree"}], ["KITCHENETTE. PRIVATE", "Westgate"])
        self.assertEqual(counts, {"Raintree": 1, "Westgate": 0})
