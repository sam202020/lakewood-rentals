"""Tests for the weekly data-quality gate (checks.py) and its use in build.py.

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

import build  # noqa: E402
import checks  # noqa: E402

TYPES = ["Apartment", "Apartment", "House", "Townhouse / Attached", "Room"]


def make(n=200, **over):
    """n plausible listings; `over` overrides fields on every listing."""
    rows = []
    for i in range(n):
        x = {
            "id": f"L{i}", "type": TYPES[i % len(TYPES)], "location": f"Raintree {i}",
            "phones": [f"732-555-{i:04d}"], "comments": "Nice place. Available immediately.",
            "rent": 2000 + i, "bedrooms_num": 2,
        }
        x.update(over)
        rows.append(x)
    return rows


class Hard(unittest.TestCase):
    def test_good_data_passes_clean(self):
        self.assertEqual(checks.check(make(), previous_count=210), ([], []))

    def test_first_run_has_no_previous_count(self):
        self.assertEqual(checks.check(make(), previous_count=None)[0], [])

    def test_too_few_listings(self):
        errors, _ = checks.check(make(40))
        self.assertTrue(any("only 40 listings" in e for e in errors))

    def test_count_collapse_vs_last_week(self):
        errors, _ = checks.check(make(150), previous_count=231)   # -35%
        self.assertTrue(any("fell" in e for e in errors))

    def test_moderate_drop_is_fine(self):
        self.assertEqual(checks.check(make(180), previous_count=231)[0], [])  # -22%

    def test_growth_is_fine(self):
        self.assertEqual(checks.check(make(300), previous_count=200)[0], [])

    def test_missing_locations(self):
        rows = make()
        for x in rows[:40]:          # 80% have a location
            x["location"] = ""
        errors, _ = checks.check(rows)
        self.assertTrue(any("location" in e for e in errors))

    def test_missing_phones(self):
        rows = make()
        for x in rows[:40]:
            x["phones"] = []
        errors, _ = checks.check(rows)
        self.assertTrue(any("phone" in e for e in errors))

    def test_a_few_gaps_are_tolerated(self):
        rows = make()
        for x in rows[:6]:           # 97% still have both
            x["location"] = ""
            x["phones"] = []
        self.assertEqual(checks.check(rows)[0], [])

    def test_a_whole_type_missing(self):
        rows = [x for x in make() if x["type"] != "House"]
        errors, _ = checks.check(rows)
        self.assertTrue(any("'House'" in e for e in errors))

    def test_the_november_regression_is_caught(self):
        """The old parser dropped ~11% of listings and lost the location on ~40%."""
        rows = make(206)
        for x in rows[:83]:
            x["location"] = ""
        errors, _ = checks.check(rows, previous_count=239)
        self.assertTrue(errors)


class Soft(unittest.TestCase):
    def test_leftover_abbreviation_warns_but_does_not_fail(self):
        rows = make()
        rows[3]["location"] = "Westgt."
        errors, warnings = checks.check(rows)
        self.assertEqual(errors, [])
        self.assertTrue(any("Westgt." in w and "rule" in w for w in warnings))

    def test_each_known_short_form_is_flagged(self):
        for raw in ("Westgt.", "New Engl. Village", "Centrl.", "W. Cnty. Ln.", "Lkwd.",
                    "Jksn.", "PLP", "Holly Oaks, Manch.", "Clubat Jackson 21", "Saratoga / TR"):
            with self.subTest(raw=raw):
                rows = make()
                rows[0]["location"] = raw
                self.assertTrue(checks.check(rows)[1], raw)

    def test_expanded_names_do_not_warn(self):
        rows = make()
        rows[0]["location"] = "Pine Lake Park, Manchester"
        rows[1]["location"] = "Club at Jackson 21"
        rows[2]["location"] = "Mackenzie Area Toms River"
        rows[3]["location"] = "Lakewood Commons Area"
        self.assertEqual(checks.check(rows), ([], []))

    def test_malformed_location_warns(self):
        rows = make()
        rows[0]["location"] = "Beautifulmodernfurnishedroom"
        self.assertTrue(any("malformed" in w for w in checks.check(rows)[1]))

    def test_many_empty_descriptions_warn(self):
        rows = make()
        for x in rows[:40]:
            x["comments"] = ""
        self.assertTrue(any("no description" in w for w in checks.check(rows)[1]))

    def test_many_glued_descriptions_warn(self):
        rows = make(comments="Beautifulnewtopofthelinefurnished home")
        self.assertTrue(any("run-together" in w for w in checks.check(rows)[1]))

    def test_rent_coverage_warns(self):
        rows = make(rent=None)
        self.assertTrue(any("numeric rent" in w for w in checks.check(rows)[1]))


class BuildGate(unittest.TestCase):
    """build.py must not write anything when a hard check fails."""

    def run_build(self, listings, existing=None):
        tmp = pathlib.Path(tempfile.mkdtemp())
        data, out = tmp / "listings.json", tmp / "index.html"
        if existing is not None:
            data.write_text(json.dumps(existing))
        out.write_text("OLD PAGE")
        with mock.patch.object(build, "DATA", data), mock.patch.object(build, "OUT", out), \
                mock.patch.object(build.P, "fetch_pdf", lambda src: src), \
                mock.patch.object(build.P, "parse", lambda f: ("Wednesday, Test 1, 2026", listings)), \
                mock.patch.object(sys, "argv", ["build.py"]):
            try:
                build.main()
                code = 0
            except SystemExit as e:
                code = e.code
        return code, data, out

    def test_bad_parse_aborts_and_leaves_files_alone(self):
        before = {"count": 231, "listings": []}
        code, data, out = self.run_build(make(120), existing=before)   # -48%
        self.assertEqual(code, 1)
        self.assertEqual(out.read_text(), "OLD PAGE")
        self.assertEqual(json.loads(data.read_text()), before)

    def test_good_parse_writes_page_and_data(self):
        code, data, out = self.run_build(make(200), existing={"count": 210, "listings": []})
        self.assertEqual(code, 0)
        self.assertNotEqual(out.read_text(), "OLD PAGE")
        self.assertEqual(json.loads(data.read_text())["count"], 200)
        self.assertIn("Raintree 7", out.read_text())

    def test_warnings_do_not_block_the_build(self):
        rows = make(200)
        rows[0]["location"] = "Westgt."
        code, _, out = self.run_build(rows)
        self.assertEqual(code, 0)
        self.assertNotEqual(out.read_text(), "OLD PAGE")


if __name__ == "__main__":
    unittest.main()
