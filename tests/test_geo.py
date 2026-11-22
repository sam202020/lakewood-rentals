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

    def test_every_resolved_place_is_near_lakewood(self):
        far = [k for k, e in self.places.items()
               if e.get("lat") is not None and not geo.plausible(e["lat"], e["lng"])]
        self.assertEqual(far, [])

    def test_entries_are_well_formed(self):
        for k, e in self.places.items():
            with self.subTest(place=k):
                self.assertIn(e["source"], ("osm", "manual", "unresolved"))
                self.assertEqual(e["lat"] is None, e["lng"] is None)
                if e["source"] == "unresolved":
                    self.assertIsNone(e["lat"])


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
