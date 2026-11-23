"""Tests for the street data (tools/build_streets.py) and how it is merged into the page (geo.streets_for_page)."""
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import build_streets as B  # noqa: E402
import geo  # noqa: E402


class Simplify(unittest.TestCase):
    def test_a_straight_street_keeps_only_its_ends(self):
        pts = [(40.0 + i * 0.001, -74.2) for i in range(10)]
        self.assertEqual(B.simplify(pts), [pts[0], pts[-1]])

    def test_a_corner_is_kept(self):
        pts = [(40.000, -74.200), (40.000, -74.199), (40.000, -74.198), (40.001, -74.198), (40.002, -74.198)]
        out = B.simplify(pts)
        self.assertIn((40.000, -74.198), out)
        self.assertEqual((out[0], out[-1]), (pts[0], pts[-1]))

    def test_short_lines_are_untouched(self):
        self.assertEqual(B.simplify([(1, 1), (2, 2)]), [(1, 1), (2, 2)])


class Naming(unittest.TestCase):
    def test_route_numbers_become_searchable_names(self):
        self.assertEqual(B.route_names({"ref": "NJ 88"}), ["Route 88"])
        self.assertEqual(B.route_names({"ref": "US 9;NJ 70"}), ["Route 9", "Route 70"])
        self.assertEqual(B.route_names({"ref": "CR 526"}), [])
        self.assertEqual(B.route_names({}), [])

    def test_same_name_far_apart_is_two_streets(self):
        lakewood = [(40.09, -74.21), (40.095, -74.21)]
        jackson = [(40.12, -74.36), (40.125, -74.36)]
        groups = B.cluster([lakewood, jackson])
        self.assertEqual(len(groups), 2)

    def test_pieces_of_one_street_stay_together(self):
        a = [(40.090, -74.21), (40.095, -74.21)]
        b = [(40.095, -74.21), (40.100, -74.21)]
        self.assertEqual(len(B.cluster([a, b])), 1)

    def test_town_label(self):
        self.assertEqual(B.town_of(40.0979, -74.2179), "Lakewood")
        self.assertEqual(B.town_of(40.1000, -74.3600), "Jackson")
        self.assertEqual(B.town_of(39.98, -74.20), "Toms River")


def street(name, lat, lng, base=(40.0, -74.4)):
    """A one-line street of two points, in the compact encoding."""
    return {"n": name, "t": "Lakewood", "p": [[round((lat - base[0]) / 1e-4), round((lng - base[1]) / 1e-4),
                                              round((lat + 0.002 - base[0]) / 1e-4), round((lng - base[1]) / 1e-4)]]}


class MergeIntoPage(unittest.TestCase):
    data = {"base": [40.0, -74.4], "unit": 1e-4,
            "streets": [street("Clover Street", 40.0905, -74.2003), street("Ocean Avenue", 40.0907, -74.2),
                        street("Route 88", 40.09, -74.2), street("Far Away Road", 40.2, -74.3)]}
    picker = [{"name": "Clover", "lat": 40.0907, "lng": -74.2003}, {"name": "Route 88", "lat": 40.09, "lng": -74.2},
              {"name": "Raintree", "lat": 40.0968, "lng": -74.1646}]

    def test_an_owner_defined_neighbourhood_beats_a_street_of_the_same_name(self):
        streets, picker = geo.streets_for_page(self.data, self.picker)
        names = [s["n"] for s in streets["streets"]]
        self.assertNotIn("Clover Street", names)
        self.assertIn("Clover", [p["name"] for p in picker])

    def test_other_streets_are_kept(self):
        streets, _ = geo.streets_for_page(self.data, self.picker)
        self.assertEqual({s["n"] for s in streets["streets"]}, {"Ocean Avenue", "Route 88", "Far Away Road"})

    def test_the_route_line_replaces_the_route_point(self):
        _, picker = geo.streets_for_page(self.data, self.picker)
        self.assertNotIn("Route 88", [p["name"] for p in picker])

    def test_same_name_but_far_away_is_a_different_street(self):
        data = dict(self.data, streets=[street("Clover Street", 40.2, -74.3)])
        streets, _ = geo.streets_for_page(data, self.picker)
        self.assertEqual([s["n"] for s in streets["streets"]], ["Clover Street"])

    def test_no_street_file_leaves_the_picker_alone(self):
        self.assertEqual(geo.streets_for_page(None, self.picker), (None, self.picker))
        self.assertEqual(geo.streets_for_page({"streets": []}, self.picker), (None, self.picker))


class ShippedStreets(unittest.TestCase):
    path = ROOT / "streets.json"

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(cls.path.read_text()) if cls.path.exists() else None

    def setUp(self):
        if self.data is None:
            self.skipTest("streets.json not built yet")

    def names(self):
        return {s["n"] for s in self.data["streets"]}

    def test_well_known_streets_are_present(self):
        for n in ("Ocean Avenue", "Clifton Avenue", "Madison Avenue", "Cedar Bridge Avenue", "Route 88", "Route 9", "Route 70"):
            self.assertIn(n, self.names(), n)

    def test_every_street_has_a_town_and_at_least_one_line(self):
        for s in self.data["streets"]:
            self.assertTrue(s["t"] and s["p"] and all(len(p) >= 4 and len(p) % 2 == 0 for p in s["p"]), s["n"])

    def test_the_file_is_small_enough_to_ship_in_the_page(self):
        self.assertLess(self.path.stat().st_size, 900_000)

    def test_streets_lie_inside_the_mapped_box(self):
        b, u = self.data["base"], self.data["unit"]
        for s in self.data["streets"]:
            for p in s["p"]:
                for i in range(0, len(p), 2):
                    lat, lng = b[0] + p[i] * u, b[1] + p[i + 1] * u
                    self.assertTrue(B.SOUTH - 0.001 <= lat <= B.NORTH + 0.001 and B.WEST - 0.001 <= lng <= B.EAST + 0.001, s["n"])


if __name__ == "__main__":
    unittest.main()
