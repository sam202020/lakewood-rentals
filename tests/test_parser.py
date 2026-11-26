"""Parser tests built from real rows of the Nov. 18 2026 Masa U'Matan PDF.

Each case is a listing as pdfplumber actually saw it: a list of (text, x0, top) words, including the
awkward ones - codes with the type letters missing or a junk prefix, the bedroom digit glued onto the
code, 7-digit phone numbers, phone numbers shattered into single characters, a phone glued to the next
word, rows shifted sideways by an ad banner, and a location centred on the row below.

Run:  python3 -m unittest discover -s tests -v
Set RENTAL_PDF=/path/to/MasaRentals.pdf to also check a real PDF end to end.
"""
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parse as P  # noqa: E402


def words(*spec):
    """spec items: (text, x0, top). x1/bottom are estimated from the text length."""
    out = []
    for text, x0, top in spec:
        out.append({"text": text, "x0": float(x0), "x1": float(x0) + max(3.0, 4.4 * len(text)),
                    "top": float(top), "bottom": float(top) + 6.8})
    return out


def shattered(text, x0, top, step=5.0):
    """A string the PDF drew one character at a time."""
    return [(c, x0 + i * step, top) for i, c in enumerate(text)]


class PhoneNumbers(unittest.TestCase):
    def test_ten_digit(self):
        self.assertEqual(P.find_phones("732-921-8180"), ["732-921-8180"])
        self.assertEqual(P.find_phones("848.488.4232"), ["848-488-4232"])
        self.assertEqual(P.find_phones("7329218180"), ["732-921-8180"])

    def test_seven_digit_local_numbers_get_the_local_area_code(self):
        self.assertEqual(P.find_phones("905-0200"), ["732-905-0200"])
        self.assertEqual(P.find_phones("367-6332"), ["732-367-6332"])

    def test_a_ten_digit_number_is_not_read_as_a_local_number_plus_junk(self):
        self.assertEqual(P.find_phones("732-732-3905"), ["732-732-3905"])

    def test_two_numbers(self):
        self.assertEqual(P.find_phones("718-541-4413/908-463-3393"), ["718-541-4413", "908-463-3393"])

    def test_not_a_phone(self):
        self.assertEqual(P.find_phones("3600"), [])
        self.assertEqual(P.find_phones("Beautiful"), [])


class CodesAndTypes(unittest.TestCase):
    def m(self, code):
        return P.CODE_LOOSE.match(code)

    def test_normal_codes(self):
        for code, letters in (("11HH66_1037:11", "HH"), ("U1HH170_1044:13", "HH"), ("A998_718:3", "A"),
                              ("1A141_995:4", "A"), ("U1RR177_1056:19", "RR"), ("11TT75_1054:20", "TT")):
            self.assertEqual(self.m(code).group("type"), letters, code)

    def test_junk_prefix_before_the_type_letters(self):
        """'CfHH1114_932:15' is the Case Road listing the old parser never saw."""
        self.assertEqual(self.m("CfHH1114_932:15").group("type"), "HH")

    def test_codes_with_no_type_letters(self):
        self.assertEqual(self.m("U1166_1035:19").group("type"), "")
        self.assertEqual(self.m("1170_1044:2").group("type"), "")

    def test_bedroom_digit_glued_onto_the_code(self):
        self.assertEqual(self.m("11TT72_1049:103").group("b"), "103")        # index 10, 3 bedrooms
        self.assertEqual(self.m("1H131_977:154o").group("b"), "154")         # index 15, 4 bedrooms ("4 or 5")

    def test_type_letters_to_type(self):
        self.assertEqual(P.derive_type_letters("HH"), "House")
        self.assertEqual(P.derive_type_letters("TT"), "Townhouse / Attached")
        self.assertEqual(P.derive_type_letters("A"), "Apartment")
        self.assertEqual(P.derive_type_letters("RR"), "Room")
        self.assertEqual(P.derive_type_letters(""), "Other")


class OneListing(unittest.TestCase):
    def row(self, *spec):
        return P.parse_row(words(*spec), 1, 0)

    def test_case_road_is_its_own_listing_with_its_own_rent_and_phone(self):
        x = self.row(
            ("CfHH1114_932:15", 84, 153.3), ("7", 100, 153.3), ("5", 119, 153.3),
            ("4", 225, 153.3), ("9", 230, 153.3), ("0", 234, 153.3), ("0", 239, 153.3),
            *shattered("73", 325, 153.3, 5), ("2", 335, 153.3), ("-", 340, 153.3), ("9", 343, 153.3), ("2", 348, 153.3),
            ("1", 353, 153.3), ("-", 358, 153.3), ("8", 361, 153.3), ("1", 366, 153.3), ("8", 371, 153.3), ("0", 376, 153.3),
            ("Beautifullargehome.", 424, 153.3),
            ("CaseRoadarea", 142, 161.3),
            ("N", 228, 161.3), ("E", 232, 161.3), ("G", 235, 161.3), (".", 239, 161.3),
            *shattered("Prefertext", 331, 161.3, 4.7),
            ("Prefersmallerfamily.", 425, 161.3))
        self.assertEqual(x["type"], "House")
        self.assertEqual((x["bedrooms"], x["baths"]), ("7", "5"))
        self.assertEqual(x["location"], "Case Road Area")
        self.assertEqual(x["rent"], 4900)
        self.assertTrue(x["negotiable"])
        self.assertEqual(x["phones"], ["732-921-8180"])
        self.assertIn("Beautiful large home", x["comments"])

    def test_the_jackson_21_listing_below_it_is_a_different_listing(self):
        x = self.row(
            ("11TT73_1051:9", 85, 170.2), ("4", 100, 170.2), ("3½", 114, 170.2), ("3600", 223, 170.2),
            ("2", 325, 170.2), ("48", 330, 170.2), ("-", 340, 170.2), ("4", 343, 170.2), ("1", 348, 170.2),
            ("6-", 353, 170.2), ("6", 361, 170.2), ("7", 366, 170.2), ("92", 371, 170.2),
            ("Brand", 387, 170.2), ("new", 409, 170.2), ("Crofton", 424, 170.2), ("model.", 451, 170.2),
            ("Jackson21", 152, 177.4), ("Backs", 389, 177.4), ("up", 410, 177.4), ("to", 420, 177.4),
            ("woods.", 428, 177.4), ("Available", 453, 177.4), ("immediately.", 484, 177.4))
        self.assertEqual(x["location"], "Jackson 21")
        self.assertEqual(x["rent"], 3600)
        self.assertEqual(x["phones"], ["248-416-6792"])
        self.assertNotIn("Case", x["location"])

    def test_code_and_data_on_two_lines_with_the_type_letters_apart(self):
        """Monmouth Views: the code (no letters) sits 7pt above the 'TT 4 3½ ...' line."""
        x = self.row(
            ("U1166_1035:19", 84, 544.1), ("Brand", 393, 544.1), ("new,", 415, 544.1),
            ("TT", 86, 551.1), ("4", 100, 551.1), ("3½", 114, 551.1), ("(cid:2)", 229, 551.1),
            ("718-218-3309", 322, 551.1), ("unit,", 410, 551.1),
            ("MonmouthViews", 138, 557.7), ("Scenic", 425, 557.7))
        self.assertEqual(x["id"], "U1166_1035:19")
        self.assertEqual(x["type"], "Townhouse / Attached")
        self.assertEqual((x["bedrooms"], x["baths"]), ("4", "3½"))
        self.assertEqual(x["location"], "Monmouth Views")
        self.assertEqual(x["phones"], ["718-218-3309"])
        self.assertEqual(x["rent_display"], "Call to discuss")

    def test_row_with_no_code_at_all_still_becomes_a_listing(self):
        x = self.row(("H", 86, 219.3), ("5", 100, 219.3), ("3", 119, 219.3), ("5000", 223, 219.3),
                     ("917-620-3820", 322, 219.3), ("Furn./unfurn,", 389, 219.3),
                     ("TomsRiver", 152, 222.8), ("suite,", 396, 227.3))
        self.assertEqual(x["type"], "House")
        self.assertEqual((x["bedrooms"], x["baths"], x["rent"]), ("5", "3", 5000))
        self.assertEqual(x["location"], "Toms River")
        self.assertEqual(x["phones"], ["917-620-3820"])
        self.assertTrue(x["id"])                                     # a made-up id, never blank

    def test_bent_hook_location(self):
        x = self.row(("1170_1044:2", 85, 544.1), ("3000", 388, 544.1),
                     ("HH", 85, 551.1), ("6", 100, 551.1), ("4", 119, 551.1), ("3600", 223, 551.1),
                     ("416-676-4965", 322, 551.1), ("eat-in", 388, 551.1), ("BentHook.T.R.", 141, 558.2))
        self.assertEqual(x["location"], "Bent Hook, Toms River")
        self.assertEqual(x["phones"], ["416-676-4965"])
        self.assertEqual(x["type"], "House")

    def test_seven_digit_local_phone(self):
        x = self.row(("11HH66_1037:11", 84, 284.5), ("5", 100, 284.5), ("4", 119, 284.5), ("TomsRiver", 152, 284.5),
                     ("(cid:2)", 229, 284.5), ("905-0200", 333, 284.5), ("Large", 412, 284.5))
        self.assertEqual(x["phones"], ["732-905-0200"])

    def test_a_free_listing_is_an_ad_and_is_left_out(self):
        """Owner: the 'FREE' Hachnosas Orchim entry is an ad, not a rental."""
        self.assertIsNone(self.row(
            ("A998_718:3", 85, 300.7), ("1", 100, 300.7), ("1", 119, 300.7), ("Raintree", 158, 300.7),
            ("FREE732-814-4648", 221, 300.7), ("Hachnosas", 316, 300.7), ("Orchim", 358, 300.7),
            ("Eishel", 388, 300.7), ("Elisheva", 412, 300.7), ("apartment.", 445, 300.7)))

    def test_phone_written_in_the_rent_area_is_still_found(self):
        x = self.row(("1A1_9:3", 85, 300.7), ("1", 100, 300.7), ("1", 119, 300.7), ("Raintree", 158, 300.7),
                     ("3200", 225, 300.7), ("732-814-4648", 221, 308.0), ("Nice", 388, 300.7))
        self.assertEqual(x["phones"], ["732-814-4648"])
        self.assertEqual(x["rent"], 3200)

    def test_two_phone_lines_each_shattered(self):
        x = self.row(("11A54_1013:17", 84, 623.8), ("1", 100, 623.8), ("1", 119, 623.8), ("(cid:2)", 229, 623.8),
                     ("GEWH", 254, 623.8),
                     ("9", 335, 623.8), ("0", 340, 623.8), ("5", 345, 623.8), ("-1", 350, 623.8), ("0", 358, 623.8),
                     ("3", 363, 623.8), ("0", 368, 623.8), ("Temporary", 391, 623.8),
                     ("Ridge/NegbaSt.", 141, 631.0),
                     ("73", 326, 631.0), ("2", 336, 631.0), ("-7", 341, 631.0), ("3", 349, 631.0), ("2", 354, 631.0),
                     ("-3", 359, 631.0), ("9", 366, 631.0), ("05", 371, 631.0), ("Choson/Kalla.", 387, 631.0))
        self.assertEqual(x["phones"], ["732-905-1030", "732-732-3905"])
        self.assertEqual(x["location"], "Ridge / Negba St.")

    def test_phone_glued_to_the_first_word_of_the_comment(self):
        x = self.row(("11HH74_1053:18", 84, 509.4), ("5", 100, 509.4), ("2½", 114, 509.3),
                     ("(cid:2)", 229, 512.6), ("HarmonyHillsJksn", 134, 514.4),
                     ("646-379-04871-family", 322, 511.5), ("1-family", 385, 511.7), ("beautiful", 413, 511.7))
        self.assertEqual(x["phones"], ["646-379-0487"])

    def test_bedroom_digit_glued_onto_the_code(self):
        x = self.row(("11TT72_1049:103", 84, 364.4), ("3½", 114, 364.4), ("Jackson21", 152, 364.4),
                     ("3300", 223, 364.4), ("917-862-9504", 322, 364.4), ("Two", 390, 364.4))
        self.assertEqual(x["id"], "11TT72_1049:10")
        self.assertEqual((x["bedrooms"], x["baths"]), ("3", "3½"))

    def test_fairways_two_plus_den(self):
        x = self.row(("U1HH162_1028:192+", 84, 446.6), ("2", 119, 446.6), ("Fairways", 157, 446.6),
                     ("732-428-9614", 322, 446.6), ("55+community.", 392, 446.6), ("DEN", 98, 454.1))
        self.assertEqual((x["bedrooms"], x["baths"]), ("2", "2"))
        self.assertEqual(x["phones"], ["732-428-9614"])

    def test_the_reserve_row_with_an_ad_banner_instead_of_the_usual_cells(self):
        x = self.row(("1H131_977:154o", 85, 188.1), ("r", 107, 187.7), ("5", 105, 192.2), ("4", 114, 185.3),
                     ("TheReserve,Jackson", 124, 190.4), ("216-903-0365", 222, 187.8),
                     ("Spacious", 315, 188.6), ("furnished", 342, 188.6), ("home.", 374, 188.6),
                     ("Great", 319, 195.8), ("for", 338, 195.8), ("family", 349, 195.8))
        self.assertEqual(x["location"], "The Reserve, Jackson")
        self.assertEqual(x["phones"], ["216-903-0365"])
        self.assertEqual(x["bedrooms"], "4")
        self.assertIsNone(x["rent"])                                 # the phone must not be read as a rent
        self.assertIn("Spacious furnished home", x["comments"])

    def test_row_shifted_sideways_by_a_banner(self):
        x = self.row(("3", 133, 655.1), ("4", 117, 655.2), ("1A168_1040:0", 102, 655.2),
                     ("443-386-2101", 248, 657.3), ("Weekend", 313, 657.5), ("Hotel:Fresh", 349, 657.5),
                     ("ChestnutAcres", 149, 660.2), ("towels,", 393, 657.5))
        self.assertEqual(x["type"], "Apartment")
        self.assertEqual((x["bedrooms"], x["baths"]), ("4", "3"))
        self.assertEqual(x["location"], "Chestnut Acres")
        self.assertEqual(x["phones"], ["443-386-2101"])

    def test_weekly_rate_is_not_shown_as_monthly(self):
        x = self.row(("1A154_1016:9", 84, 177.4), ("1", 100, 177.4), ("1", 119, 177.4), ("Arlingtonarea", 146, 177.4),
                     ("600", 224, 177.4), *shattered("week", 228, 185.0), ("732-555-0101", 322, 177.4))
        self.assertIsNone(x["rent"])
        self.assertEqual(x["rent_display"], "$600/week")
        self.assertEqual(x["rent_period"], "week")

    def test_rent_digits_the_pdf_drew_separately_are_rejoined(self):
        x = self.row(("1HH1_1:1", 84, 10), ("3", 100, 10), ("2", 119, 10), ("Raintree", 158, 10),
                     ("3", 225, 10), ("2", 230, 10), ("0", 234, 10), ("0", 239, 10),
                     ("732-555-0101", 322, 10))
        self.assertEqual(x["rent"], 3200)

    def test_a_listing_with_two_phones_stacked_keeps_both(self):
        x = self.row(("U1TT175_1054:7", 84, 436.3), ("3", 100, 436.3), ("1½", 114, 436.3), ("RoseCt.", 158, 436.3),
                     ("718-541-4413", 322, 436.3), ("908-463-3393", 322, 443.0))
        self.assertEqual(x["phones"], ["718-541-4413", "908-463-3393"])

    def test_ad_banner_is_not_a_listing(self):
        self.assertIsNone(self.row(("1149_1005:0", 85, 267.9), ("BRAND", 167, 267.9), ("NEW", 193, 267.9),
                                   ("GUEST", 211, 267.9), ("SUITE", 234, 267.9), ("CALL", 357, 275.1),
                                   ("732-267-3594", 406, 275.1)))

    def test_header_row_is_not_a_listing(self):
        self.assertIsNone(self.row(("Type", 83, 125.7), ("BR", 100, 125.7), ("Location", 152, 125.7),
                                   ("Telephone", 329, 125.7)))


class FakePage:
    """Just enough of a pdfplumber page for _parse_page_by_cells / row_cells."""

    def __init__(self, ws, rects):
        self._ws, self.rects = ws, rects

    def extract_words(self, keep_blank_chars=False, use_text_flow=False):
        return list(self._ws)


def rect(x0, x1, top, bottom):
    return {"x0": x0, "x1": x1, "top": top, "bottom": bottom, "height": bottom - top}


class RowsFromCells(unittest.TestCase):
    def cells(self, tops, with_loc=True):
        out = []
        for t in tops:
            for a, b in ((83, 97), (97, 112), (112, 133)) + (((133, 220),) if with_loc else ()):
                out.append(rect(a, b, t, t + 16.2))
        return out

    def test_row_bands_come_from_the_left_hand_cells(self):
        page = FakePage([], self.cells([100, 116.2, 132.4]))
        self.assertEqual(P.row_cells(page), [(100.0, 116.2), (116.2, 132.4), (132.4, 148.6)])

    def test_a_banner_that_hides_the_location_cell_still_gives_a_band(self):
        page = FakePage([], self.cells([100], with_loc=False))
        self.assertEqual(P.row_cells(page), [(100.0, 116.2)])

    def test_no_cells_means_no_bands(self):
        self.assertEqual(P.row_cells(FakePage([], [])), [])

    def test_two_neighbours_stay_two_listings(self):
        """The Case Road / Jackson 21 bug: rows are separated by the table cells, not by guessing."""
        ws = words(("HH1_1:1", 84, 102), ("7", 100, 102), ("5", 119, 102), ("CaseRoadarea", 142, 108),
                   ("4900", 223, 102), ("732-921-8180", 322, 102),
                   ("11TT73_1051:9", 85, 118), ("4", 100, 118), ("3½", 114, 118), ("Jackson21", 152, 124),
                   ("3600", 223, 118), ("248-416-6792", 322, 118))
        page = FakePage(ws, self.cells([100, 116.2]))
        got = P._parse_page_by_cells(page, P.row_cells(page), 1)
        self.assertEqual([x["location"] for x in got], ["Case Road Area", "Jackson 21"])
        self.assertEqual([x["phones"] for x in got], [["732-921-8180"], ["248-416-6792"]])
        self.assertEqual([x["rent"] for x in got], [4900, 3600])


@unittest.skipUnless(os.environ.get("RENTAL_PDF"), "set RENTAL_PDF to check a real PDF")
class RealPdf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.date, cls.rows = P.parse(os.environ["RENTAL_PDF"])

    def test_every_listing_has_a_phone_a_type_and_bedrooms(self):
        self.assertGreater(len(self.rows), 200)
        for x in self.rows:
            self.assertTrue(x["phones"], x["id"])
            self.assertNotEqual(x["type"], "Other", x["id"])
            self.assertTrue(x["bedrooms"], x["id"])

    def test_ids_are_unique(self):
        ids = [x["id"] for x in self.rows]
        self.assertEqual(len(ids), len(set(ids)))


class BrookwoodSpelledOut(unittest.TestCase):
    """Owner 2026-11-26: write Brookwood out; "outside Brookwood" belongs to Brookwood."""

    def test_location_is_spelled_out(self):
        for raw, want in [("Outside Brookwd 1", "Brookwood 1"), ("Brookwd 3", "Brookwood 3"), ("Brookwood 4 Jackson", "Brookwood 4 Jackson")]:
            self.assertEqual(P.clean_loc(raw)[0], want, raw)


if __name__ == "__main__":
    unittest.main()
