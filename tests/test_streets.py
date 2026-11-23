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


class Encoding(unittest.TestCase):
    def test_round_trip(self):
        pts = [(40.0900, -74.2000), (40.0912, -74.1985), (40.0930, -74.1990)]
        back = B.decode(B.encode(pts))
        for (a, b), (c, d) in zip(pts, back):
            self.assertAlmostEqual(a, c, places=4)
            self.assertAlmostEqual(b, d, places=4)

    def test_steps_are_small_numbers(self):
        flat = B.encode([(40.0900, -74.2000), (40.0912, -74.1985)])
        self.assertEqual(flat[2:], [12, 15])

    def test_pieces_sharing_an_end_are_joined(self):
        a = [(40.09, -74.21), (40.095, -74.21)]
        b = [(40.095, -74.21), (40.10, -74.21)]
        joined = B.join_paths([a, b])
        self.assertEqual(joined, [[(40.09, -74.21), (40.095, -74.21), (40.10, -74.21)]])

    def test_pieces_in_the_wrong_direction_are_joined_too(self):
        a = [(40.09, -74.21), (40.095, -74.21)]
        b = [(40.10, -74.21), (40.095, -74.21)]
        self.assertEqual(len(B.join_paths([a, b])[0]), 3)

    def test_unconnected_pieces_stay_separate(self):
        a = [(40.09, -74.21), (40.095, -74.21)]
        b = [(40.20, -74.21), (40.21, -74.21)]
        self.assertEqual(len(B.join_paths([a, b])), 2)


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
    """A one-line street of two points, in the compact encoding [name, town index, [path]]."""
    la, ln = round((lat - base[0]) / 1e-4), round((lng - base[1]) / 1e-4)
    return [name, 0, [[la, ln, 20, 0]]]                      # first point, then a 20-unit step north


class MergeIntoPage(unittest.TestCase):
    data = {"base": [40.0, -74.4], "unit": 1e-4, "towns": ["Lakewood"],
            "streets": [street("Clover Street", 40.0905, -74.2003), street("Ocean Avenue", 40.0907, -74.2),
                        street("Route 88", 40.09, -74.2), street("Far Away Road", 40.2, -74.3),
                        street("East 7th Street", 40.0985, -74.1992)]}
    picker = [{"name": "Clover", "lat": 40.0907, "lng": -74.2003}, {"name": "Route 88", "lat": 40.09, "lng": -74.2},
              {"name": "Raintree", "lat": 40.0968, "lng": -74.1646}, {"name": "E 7th Street", "lat": 40.0985, "lng": -74.1992}]

    def flags(self, streets):
        return {s[0]: len(s) > 3 for s in streets["streets"]}

    def test_a_street_named_like_an_owner_neighbourhood_is_flagged_not_dropped(self):
        streets, picker = geo.streets_for_page(self.data, self.picker)
        flags = self.flags(streets)
        self.assertTrue(flags["Clover Street"])                 # kept: "Clover & Ocean" needs its lines
        self.assertIn("Clover", [p["name"] for p in picker])

    def test_abbreviated_directions_count_as_the_same_name(self):
        streets, _ = geo.streets_for_page(self.data, self.picker)
        self.assertTrue(self.flags(streets)["East 7th Street"])   # picker has "E 7th Street"

    def test_other_streets_are_kept_unflagged(self):
        streets, _ = geo.streets_for_page(self.data, self.picker)
        flags = self.flags(streets)
        self.assertFalse(flags["Ocean Avenue"])
        self.assertFalse(flags["Far Away Road"])
        self.assertEqual(len(streets["streets"]), 5)

    def test_the_route_line_replaces_the_route_point(self):
        _, picker = geo.streets_for_page(self.data, self.picker)
        self.assertNotIn("Route 88", [p["name"] for p in picker])

    def test_same_name_but_far_away_is_a_different_street(self):
        data = dict(self.data, streets=[street("Clover Street", 40.2, -74.3)])
        streets, _ = geo.streets_for_page(data, self.picker)
        self.assertFalse(self.flags(streets)["Clover Street"])

    def test_no_street_file_leaves_the_picker_alone(self):
        self.assertEqual(geo.streets_for_page(None, self.picker), (None, self.picker))
        self.assertEqual(geo.streets_for_page({"streets": []}, self.picker), (None, self.picker))

    def test_directions_are_normalised(self):
        self.assertEqual(geo._base("E 7th Street"), geo._base("East 7th Street"))
        self.assertEqual(geo._base("W. County Line Road"), geo._base("West County Line Road"))


class ShippedStreets(unittest.TestCase):
    path = ROOT / "streets.json"

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(cls.path.read_text()) if cls.path.exists() else None

    def setUp(self):
        if self.data is None:
            self.skipTest("streets.json not built yet")

    def names(self):
        return {s[0] for s in self.data["streets"]}

    def test_well_known_streets_are_present(self):
        for n in ("Ocean Avenue", "Clifton Avenue", "Madison Avenue", "Cedar Bridge Avenue", "Route 88", "Route 9", "Route 70",
                  "Ridge Avenue", "Clover Street", "Nowlan Place", "Princeton Avenue", "Lexington Avenue", "Squankum Road",
                  "New Hampshire Avenue", "Vermont Avenue", "Massachusetts Avenue", "James Street", "Chestnut Street"):
            self.assertIn(n, self.names(), n)

    def test_every_street_has_a_town_and_at_least_one_line(self):
        for s in self.data["streets"]:
            self.assertTrue(0 <= s[1] < len(self.data["towns"]) and s[2] and
                            all(len(p) >= 4 and len(p) % 2 == 0 for p in s[2]), s[0])

    def test_streets_match_google_maps(self):
        """Spot-check (2026-11-22): the point Google Maps gives for each street lies on our line for it."""
        google = {"Cedar Bridge Avenue": (40.07096, -74.1724738), "Madison Avenue": (40.0982642, -74.217881),
                  "Clifton Avenue": (40.0989751, -74.2159162), "Squankum Road": (40.1051805, -74.2052555),
                  "New Hampshire Avenue": (40.0567628, -74.1956492), "Vermont Avenue": (40.0648696, -74.2067403)}
        for name, (lat, lng) in google.items():
            near = min(geo.miles_to_street(self.data, s, lat, lng) for s in self.data["streets"] if s[0] == name)
            self.assertLess(near, 0.05, name)

    def test_laurel_avenue_is_where_415_laurel_ave_is(self):
        lat, lng = 40.0899592, -74.1991014            # Google Maps: 415 Laurel Ave, Lakewood
        near = min(geo.miles_to_street(self.data, s, lat, lng) for s in self.data["streets"] if s[0] == "Laurel Avenue")
        self.assertLess(near, 0.1)

    def test_a_street_in_two_towns_is_two_entries_and_one_town_has_one(self):
        keys = [(s[0], s[1]) for s in self.data["streets"]]
        self.assertEqual(len(keys), len(set(keys)))        # the same name in the same town is one street

    def test_the_file_is_small_enough_to_ship_in_the_page(self):
        self.assertLess(self.path.stat().st_size, 450_000)

    def test_only_streets_near_lakewood_are_kept(self):
        for s in self.data["streets"]:
            pts = geo._street_points(self.data, s)
            la = sum(p[0] for p in pts) / len(pts)
            ln = sum(p[1] for p in pts) / len(pts)
            self.assertLess(geo.haversine_miles(la, ln, *B.CENTER), B.MAX_MILES + 0.5, s[0])

    def test_streets_lie_inside_the_mapped_box(self):
        for s in self.data["streets"]:
            for lat, lng in geo._street_points(self.data, s):
                # a street that crosses the edge of the downloaded box keeps its whole shape (a few hundredths of a degree)
                self.assertTrue(B.SOUTH - 0.06 <= lat <= B.NORTH + 0.06 and B.WEST - 0.06 <= lng <= B.EAST + 0.06, s[0])


if __name__ == "__main__":
    unittest.main()
