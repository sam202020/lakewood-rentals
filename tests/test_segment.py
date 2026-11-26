"""Tests for putting spaces back into words the PDF ran together (segment.py) and its use in descriptions."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import checks  # noqa: E402
import parse as P  # noqa: E402
import segment  # noqa: E402

# real run-together words from the Nov. 18 2026 PDF -> what the PDF meant
GLUED = {
    "Beautifulnewtopofthelinefurnished": "Beautiful new top of the line furnished",
    "locationneareverything": "location near everything",
    "immediatelytill": "immediately till",
    "inyard": "in yard",
    "heatedpoolonfrum": "heated pool on frum",
    "Availablethrough": "Available through",
    "Shorttermluxury": "Short term luxury",
    "Beautifulfurnishedapt": "Beautiful furnished apt",
    "Largewindows": "Large windows",
    "roomwithbathroomforsinglemale": "room with bathroom for single male",
    "Stainlesssteelappliances": "Stainless steel appliances",
    "Fullyrenovatedbilevel": "Fully renovated bilevel",
    "viewsallaround": "views all around",
    "Needincomecredentials": "Need income credentials",
    "Andrewmodel": "Andrew model",
    "cargarage": "car garage",
    "Prefersmallerfamily": "Prefer smaller family",
    "largelivingarea": "large living area",
    "Furnishedhousew": "Furnished house w",
    "Kallahabove": "Kallah above",
}


class Split(unittest.TestCase):
    def test_real_run_together_words_are_split(self):
        for glued, fixed in GLUED.items():
            self.assertEqual(" ".join(segment.split_token(glued) or [glued]), fixed, glued)

    def test_capitals_are_kept_where_they_were(self):
        self.assertEqual(segment.split_token("Beautifullayout"), ["Beautiful", "layout"])

    def test_a_known_word_is_never_split(self):
        for w in ("immediately", "available", "furnished", "weekdays", "apartment", "basemt", "unfurnished",
                  "yellowstone", "Beautifully", "Kitchenette", "Choson", "Shabbosim", "construction"):
            self.assertIsNone(segment.split_token(w), w)

    def test_unknown_names_and_words_are_left_alone(self):
        for w in ("Crofton", "Hachnosas", "Elisheva", "Sephardic", "Xyzzyplugh"):
            self.assertIsNone(segment.split_token(w), w)

    def test_a_token_is_split_only_when_every_piece_is_a_word(self):
        self.assertIsNone(segment.split_token("furnishedxqzv"))
        self.assertIsNone(segment.split_token("zzfurnishedapt"))

    def test_short_tokens_and_numbers_are_ignored(self):
        self.assertEqual(segment.fix_glued("2-car 3mo. W/D 1st"), "2-car 3mo. W/D 1st")

    def test_text_outside_the_glued_words_is_untouched(self):
        self.assertEqual(segment.fix_glued("Nice, quiet; Choson/Kallah. $1,200!"), "Nice, quiet; Choson/Kallah. $1,200!")

    def test_a_single_letter_is_never_a_trailing_fragment(self):
        # "largelivingarea" must not become "large living are a"
        self.assertEqual(segment.split_token("largelivingarea"), ["large", "living", "area"])


class Hyphenated(unittest.TestCase):
    def test_a_word_broken_across_lines_is_rejoined(self):
        self.assertEqual(segment.join_hyphenated("very safe environ- ment. In Eruv"), "very safe environment. In Eruv")
        self.assertEqual(segment.join_hyphenated("working/learn- ing guys"), "working/learning guys")

    def test_real_hyphens_between_words_are_kept(self):
        self.assertEqual(segment.join_hyphenated("well- kept and move-in ready"), "well- kept and move-in ready")
        self.assertEqual(segment.join_hyphenated("fully-furnished, 2-car"), "fully-furnished, 2-car")

    def test_in_a_description(self):
        self.assertEqual(P.clean_comment("sidewalks on both sides, very safe environ- ment."),
                         "sidewalks on both sides, very safe environment.")


class InDescriptions(unittest.TestCase):
    def test_whole_descriptions(self):
        cases = {
            "Furnishedfor Choson/Kallah,near shuls. Beautifullayout. Shorttermuntil Dec.30.":
                "Furnished for Choson/Kallah, near shuls. Beautiful layout. Short term until December 30.",
            "Beautifulnewtopofthelinefurnished.Great locationneareverything.Av.immediately.":
                "Beautiful new top of the line furnished. Great location near everything. Available immediately.",
            "Beautifuldeck, 2-sinkkitchen,finishedbasemt.2-cargarage. Pool.":
                "Beautiful deck, 2-sink kitchen, finished basement. 2-car garage. Pool.",
            "Single-family home,freshly renovated. Nice fenced-inyard. Av.immediatelytill July.":
                "Single-family home, freshly renovated. Nice fenced-in yard. Available immediately till July.",
        }
        for raw, want in cases.items():
            self.assertEqual(P.clean_comment(raw), want)

    def test_properly_spaced_text_is_unchanged(self):
        text = "Brand new. Available immediately. Furnished/unfurnished, ultra-modern kitchen, master suite."
        self.assertEqual(P.clean_comment(text), text)

    def test_ordinary_abbreviations_and_decimals_keep_their_shape(self):
        self.assertEqual(P.clean_comment("3000 s.f, 2.5 baths, e.g. A/C."), "3000 square feet, 2.5 baths, e.g. A/C.")


class Gate(unittest.TestCase):
    def rows(self, comment):
        return [{"id": f"L{i}", "type": ["Apartment", "House", "Townhouse / Attached"][i % 3], "location": f"Raintree {i}",
                 "phones": ["732-555-0101"], "comments": comment, "rent": 2000, "bedrooms_num": 2} for i in range(100)]

    def test_a_long_unknown_word_is_flagged_not_blocked(self):
        errors, warnings = checks.check(self.rows("Nice home with sparklingbluewhateverness nearby."))
        self.assertEqual(errors, [])
        self.assertTrue(any("sparklingbluewhateverness" in w for w in warnings))

    def test_known_long_words_are_not_flagged(self):
        self.assertFalse(any("run together" in w and "missing from" in w
                             for w in checks.check(self.rows("Available immediately. Beautifully renovated apartment."))[1]))


class SplitAfterFirstLetter(unittest.TestCase):
    """Owner 2026-11-26: stray spaces in descriptions ("P artly-furnished", "o r whole house", "I nternet")."""

    def test_real_rows_are_rejoined(self):
        for raw, want in [("P artly-furnished room", "Partly-furnished room"), ("by the room, o r whole house", "by the room, or whole house"),
                          ("I nternet included.", "Internet included."), ("Walking distance to 2 s huls.", "Walking distance to 2 shuls.")]:
            self.assertEqual(segment.rejoin_split_words(raw), want)

    def test_real_separate_words_are_left_alone(self):
        for text in ["near R\u2019Lubin\u2019s shul.", "Apt. B upstairs.", "a room in a house", "I need it", "Unit B for rent", "2 BR & a den"]:
            self.assertEqual(segment.rejoin_split_words(text), text)


class RunTogetherWordsFromNov25(unittest.TestCase):
    """Owner 2026-11-26: "Chasunanight", "Stunninggrounds", "Lowintroductoryrates"."""

    def test_real_words_are_split(self):
        for raw, want in [("Chasunanight.", "Chasuna night."), ("Stunninggrounds.", "Stunning grounds."),
                          ("Lowintroductoryrates.", "Low introductory rates.")]:
            self.assertEqual(segment.fix_glued(raw), want)
        self.assertEqual(segment.fix_glued("R\u2019Jacobovits\u2019s Shul"), "R\u2019Jacobovits\u2019s Shul")


if __name__ == "__main__":
    unittest.main()
