"""Tests for the location naming rules in parse.py (PLACE_NAMES / ABBREVIATIONS).

Run:  python3 -m unittest discover -s tests -v
"""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parse as P  # noqa: E402


def loc(raw):
    return P.clean_loc(raw)[0]


class PlaceNames(unittest.TestCase):
    def check(self, expected, *variants):
        for raw in variants:
            with self.subTest(raw=raw):
                self.assertEqual(loc(raw), expected)

    def test_club_at_jackson_21(self):
        self.check("Club at Jackson 21",
                   "ClubatJackson21", "Clubat Jackson 21", "Club at Jackson21",
                   "Club at Jackson 21", "club at jackson 21")

    def test_mackenzie_area_toms_river(self):
        self.check("Mackenzie Area Toms River",
                   "MackenzieareaTR", "Mackenzie area T.R.", "MackenzieareaToms River",
                   "Mackenzie Area Toms R.", "Mackenzie Area Toms River")

    def test_lakewood_commons_area(self):
        self.check("Lakewood Commons Area",
                   "Lkwd.Comm.Area", "Lkwd. Comm. Area", "Lkwd.Commons Area")

    def test_lakewood_commons_without_area(self):
        self.check("Lakewood Commons", "Lkwd.Comm.")

    def test_lakewood_area_is_left_alone(self):
        self.check("Lakewood Area", "Lakewood Area", "Lakewoodarea")

    def test_westgate(self):
        self.check("Westgate", "Westgt.", "Westgt", "West Gate", "Westgate")

    def test_westgate_glued_to_previous_word(self):
        self.check("Lutzk near Westgate", "LutzknearWestgt.", "Lutzk near Westgt.")


class Abbreviations(unittest.TestCase):
    def test_toms_river(self):
        self.assertEqual(loc("Whitewater Ct./T.R."), "Whitewater Ct. / Toms River")
        self.assertEqual(loc("Saratoga/TR"), "Saratoga / Toms River")
        self.assertEqual(loc("Crest Hill, Toms R."), "Crest Hill, Toms River")

    def test_jackson(self):
        self.assertEqual(loc("Dunhill Rd, Jksn."), "Dunhill Rd, Jackson")

    def test_lakewood(self):
        self.assertEqual(loc("Ivy Hill Rd.Lkwd."), "Ivy Hill Rd. Lakewood")

    def test_england_central_county(self):
        self.assertEqual(loc("New Engl.Village"), "New England Village")
        self.assertEqual(loc("New Engl. Village"), "New England Village")
        self.assertEqual(loc("St.Nicholas/Centrl."), "St. Nicholas / Central")
        self.assertEqual(loc("Centrl. Ave."), "Central Ave.")
        self.assertEqual(loc("W.Cnty.Ln."), "W. County Ln.")
        self.assertEqual(loc("W.Cnty. Ln. / Hope"), "W. County Ln. / Hope")
        self.assertEqual(loc("Cnty Line"), "County Line")

    def test_directional_initials(self):
        self.assertEqual(loc("County Ln/NApple"), "County Ln / N. Apple")
        self.assertEqual(loc("SBrook"), "S. Brook")
        self.assertEqual(loc("N.Oakland/Ocean"), "N. Oakland / Ocean")

    def test_directional_rule_leaves_other_words_alone(self):
        for name in ("NJ", "Newark", "Northgate", "East End", "West Park", "Sunset"):
            self.assertEqual(loc(name), name)

    def test_full_words_are_untouched(self):
        for name in ("England", "Central", "County Line", "Central Lakewood", "New England Village"):
            self.assertEqual(loc(name), name)

    def test_tr_is_case_sensitive(self):
        # ordinary words must never be rewritten
        self.assertEqual(loc("Trinity"), "Trinity")
        self.assertEqual(loc("Forest tr"), "Forest tr")


class General(unittest.TestCase):
    def test_idempotent(self):
        for raw in ["ClubatJackson21", "MackenzieareaTR", "Lkwd.Comm.Area", "LutzknearWestgt.",
                    "Whitewater Ct./T.R.", "Ridgearea", "St.Katherine/Hope"]:
            with self.subTest(raw=raw):
                once = loc(raw)
                self.assertEqual(loc(once), once)

    def test_ordinary_locations_unchanged(self):
        for name in ["Raintree", "Brook Hill", "Toms River", "Jackson 21", "Henry Street",
                     "Oak & Vine", "13th & Princeton"]:
            with self.subTest(name=name):
                self.assertEqual(loc(name), name)

    def test_area_suffix_is_capitalised_and_spaced(self):
        self.assertEqual(loc("Ridgearea"), "Ridge Area")
        self.assertEqual(loc("14thStreetarea"), "14th Street Area")

    def test_phone_numbers_are_split_out_of_locations(self):
        text, phones = P.clean_loc("Regency Call or310-299-6214")
        self.assertEqual(text, "Regency")
        self.assertEqual(phones, ["310-299-6214"])


class ShippedData(unittest.TestCase):
    """The current listings.json / built page must not contain raw abbreviations."""

    @classmethod
    def setUpClass(cls):
        cls.listings = json.loads((ROOT / "listings.json").read_text())["listings"]

    def test_no_unexpanded_abbreviations(self):
        bad = re.compile(r"\bWestgt\b|\bEngl\b|\bCentrl\b|\bCnty\b|\bLkwd\b|\bJksn\b|\bT\.?R\.?\b|\bClubat\b|\bToms R\.?$")
        offenders = [(x["id"], x["location"]) for x in self.listings if bad.search(x["location"])]
        self.assertEqual(offenders, [])

    def test_every_listing_has_a_location(self):
        self.assertEqual([x["id"] for x in self.listings if not x["location"]], [])

    def test_the_named_places_appear_in_current_data(self):
        names = {x["location"] for x in self.listings}
        for expected in ("Club at Jackson 21", "Mackenzie Area Toms River",
                         "Lakewood Commons Area", "Westgate"):
            with self.subTest(expected=expected):
                self.assertIn(expected, names)


class SiteTitle(unittest.TestCase):
    def test_page_says_lakewood_nj_area(self):
        page = (ROOT / "docs" / "index.html").read_text()
        self.assertIn("<title>Lakewood NJ Area Rentals</title>", page)
        self.assertIn("The Lakewood NJ Area Rental List", page)
        self.assertNotIn("Lakewood &amp; Jackson", page)


if __name__ == "__main__":
    unittest.main()
