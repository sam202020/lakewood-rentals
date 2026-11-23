"""Tests for spelling out the abbreviations in descriptions (abbrev.py). Cases are real descriptions from the
Nov. 18 2026 list plus the tricky ones: abbreviations with two meanings, full stops, and capitals."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import abbrev  # noqa: E402
import parse as P  # noqa: E402

E = abbrev.expand

# (what the PDF says, what the site should say)
REAL = [
    ("Beautiful upgraded furnished apt. for Choson/Kallah. Must see. Av. immediately.",
     "Beautiful upgraded furnished apartment for Choson/Kallah. Must see. Available immediately."),
    ("Beautiful. Finished basement, stunning backyard. Short/long term. Av. imm.",
     "Beautiful. Finished basement, stunning backyard. Short/long term. Available immediately."),
    ("Very well kept, upgraded kitchen, suite on lower level, close to Shuls. Av. Av. imm.",
     "Very well kept, upgraded kitchen, suite on lower level, close to Shuls. Available immediately."),
    ("Beautifully furnished home, lg. bkyd., with heated pool, new appli., also winter rental.",
     "Beautifully furnished home, large backyard, with heated pool, new appliances, also winter rental."),
    ("Beautifully remodeled, furn./unfurn. largest model, lg. bkyd., minyan. Av. immediately.",
     "Beautifully remodeled, furnished/unfurnished largest model, large backyard, minyan. Available immediately."),
    ("Great, 55+. 2 floors. LR/Dr, lg. family room & den. Patio. Appliances. All amenities inc.",
     "Great, 55+. 2 floors. Living room/dining room, large family room & den. Patio. Appliances. All amenities included."),
    ("On nice block. Full unfinished basement. In-ground pool. Freshly painted. Av. Dec. 1.",
     "On nice block. Full unfinished basement. In-ground pool. Freshly painted. Available December 1."),
    ("Legal apt. 9-ft. ceiling. Eat-in kitchen. Large dining room/living room. Av. imm.",
     "Legal apartment. 9-foot ceiling. Eat-in kitchen. Large dining room/living room. Available immediately."),
    ("Beautiful upgraded furnished, Heimishe area. 10 ft. ceilings. Av. immediately.",
     "Beautiful upgraded furnished, Heimishe area. 10-foot ceilings. Available immediately."),
    ("Beautifully updated ranch. Multiple minyanim 10 min. walk, low utilities. Opt. furnished.",
     "Beautifully updated ranch. Multiple minyanim 10-minute walk, low utilities. Optionally furnished."),
    ("Howell. Santino model, new construction, approx. 2300 sq. ft. Has deck. Av. imm.",
     "Howell. Santino model, new construction, approximately 2300 square feet. Has deck. Available immediately."),
    ("Beautiful spacious new furnished. Large BR, large EIK. Separate LR. WD. Av. imm.",
     "Beautiful spacious new furnished. Large bedroom, large eat-in kitchen. Separate living room. Washer/dryer. Available immediately."),
    ("Furnished house w/priv. heated pool on frum block. Available through June.",
     "Furnished house with private heated pool on frum block. Available through June."),
    ("Must see! Bright/airy furnished. Upgr. thru-out. Near Shuls/shopping. Full kitchen.",
     "Must see! Bright/airy furnished. Upgraded throughout. Near Shuls/shopping. Full kitchen."),
    ("Furnished temporary apartment. No WD. Excellent price. Available immediately.",
     "Furnished temporary apartment. No washer/dryer. Excellent price. Available immediately."),
    ("Small newer furnished/unfurn. Full kitchen, 2 sinks, WD. Perf. for single/office. Av. imm.",
     "Small newer furnished/unfurnished. Full kitchen, 2 sinks, washer/dryer. Perfect for single/office. Available immediately."),
    ("Furn. temporary end unit, many upgrades. Nice layout. Large EIK. Av. beginning Dec.",
     "Furnished temporary end unit, many upgrades. Nice layout. Large eat-in kitchen. Available beginning December."),
    ("Beautiful new fully-furnished short term, not far from Mordy's shteibel. Avoid Rt. 9.",
     "Beautiful new fully-furnished short term, not far from Mordy's shteibel. Avoid Route 9."),
    ("Furnished Choson/Kallah. E. Kennedy area, near Shuls & shopping. Av. immediately.",
     "Furnished Choson/Kallah. East Kennedy area, near Shuls & shopping. Available immediately."),
    ("Magnificent fully upgraded furn. Choson/ Kallah apt. with custom closets. Av. imm.",
     "Magnificent fully upgraded furnished Choson/Kallah apartment with custom closets. Available immediately."),
    ("Beautiful freshly redone ranch, brand new SS appliances. Full unfin. bsmt. with bath.",
     "Beautiful freshly redone ranch, brand new stainless steel appliances. Full unfinished basement with bath."),
    ("Beautiful furnished apt. Large windows. St. steel kitchen. WD. Perfect for Choson/Kallah.",
     "Beautiful furnished apartment. Large windows. Stainless steel kitchen. Washer/dryer. Perfect for Choson/Kallah."),
    ("Furn. room with bathroom for single male. Fridge, freezer, WD. Priv. entrance. Av. imm.",
     "Furnished room with bathroom for single male. Fridge, freezer, washer/dryer. Private entrance. Available immediately."),
    ("Partly-furn. room, single working guys apt., quiet block. New, near shopping. Inc. wifi.",
     "Partly-furnished room, single working guys apartment, quiet block. New, near shopping. Includes wifi."),
    ("3000 s.f, Large bedrms, spacious backyard, eat-in kitchen.",
     "3000 square feet, Large bedrooms, spacious backyard, eat-in kitchen."),
    ("Completely remodeled 3600 SF., on acre lot, fenced, full unfinished bsmt., cul-de-sac.",
     "Completely remodeled 3600 square feet, on acre lot, fenced, full unfinished basement, cul-de-sac."),
    ("Brand new lg. Crofton model w/ gorgeous lg. bkyd. walkout bsmt. Long term. Av. imm.",
     "Brand new large Crofton model with gorgeous large backyard walkout basement. Long term. Available immediately."),
    ("Br. new beautiful spacious furnished. Av. imm.", "Brand new beautiful spacious furnished. Available immediately."),
    ("2000+ sq. ft. Recently fully renovated. Lg lot. Av. mid-Nov. long term.",
     "2000+ square feet. Recently fully renovated. Large lot. Available mid-November long term."),
    ("Move-in ready. 1 mo. deposit. 3mo. minimum.", "Move-in ready. 1 month deposit. 3 months minimum."),
    ("Completely brand new interior, double story kitchen & LR/DR. Avail. November.",
     "Completely brand new interior, double story kitchen & living room/dining room. Available November."),
    ("Walking dist. to 2 shuls. Near Hope Chapel & E. Veterans.", "Walking distance to 2 shuls. Near Hope Chapel & East Veterans."),
    ("Laurel Ave./Ocean Ave. Available immediately. Single home 3rd Ave. Finished basement.",
     "Laurel Avenue/Ocean Avenue. Available immediately. Single home 3rd Avenue. Finished basement."),
    ("Separate AC. WD in basement.", "Separate air conditioning. Washer/dryer in basement."),
]


class RealDescriptions(unittest.TestCase):
    def test_real_descriptions(self):
        for raw, want in REAL:
            self.assertEqual(E(raw), want, raw)


class TwoMeanings(unittest.TestCase):
    def test_sep_is_september_before_a_number_and_separate_before_a_word(self):
        self.assertEqual(E("Av. Sep. 1."), "Available September 1.")
        self.assertEqual(E("Sunny, large windows. Sep. kitchen & family room."), "Sunny, large windows. Separate kitchen & family room.")

    def test_min_is_minutes_before_walk_and_minimum_otherwise(self):
        self.assertEqual(E("10 min. walk to shul"), "10-minute walk to shul")
        self.assertEqual(E("1 min drive to the park"), "1-minute drive to the park")
        self.assertEqual(E("3 mo. min."), "3 months minimum.")

    def test_inc_is_includes_at_the_start_of_a_sentence_and_included_after_a_noun(self):
        self.assertEqual(E("Quiet block. Inc. wifi."), "Quiet block. Includes wifi.")
        self.assertEqual(E("Internet incl. No contact."), "Internet included. No contact.")
        self.assertEqual(E("All amenities inc."), "All amenities included.")

    def test_poss_is_possibly_before_a_word_and_possible_otherwise(self):
        self.assertEqual(E("Poss. furnished master bedroom."), "Possibly furnished master bedroom.")
        self.assertEqual(E("Also office/poss."), "Also office/possible.")

    def test_ft_is_foot_before_ceilings_and_feet_otherwise(self):
        self.assertEqual(E("9-ft. ceiling"), "9-foot ceiling")
        self.assertEqual(E("10 ft. ceilings."), "10-foot ceilings.")
        self.assertEqual(E("3100 sq. feet."), "3100 square feet.")
        self.assertEqual(E("1500 ft. lot"), "1500 feet lot")

    def test_one_bedroom_is_singular(self):
        self.assertEqual(E("1 BR, 2 BR, 3bd."), "1 bedroom, 2 bedrooms, 3 bedrooms.")


class FullStopsAndCapitals(unittest.TestCase):
    def test_the_abbreviations_own_stop_goes_mid_sentence_and_stays_at_the_end(self):
        self.assertEqual(E("Furn. apt. near shul. Great location."), "Furnished apartment near shul. Great location.")
        self.assertEqual(E("Beautiful apt. Great location."), "Beautiful apartment. Great location.")
        self.assertEqual(E("Nice apt., fully upgraded."), "Nice apartment, fully upgraded.")
        self.assertEqual(E("Beautiful furnished apt."), "Beautiful furnished apartment.")

    def test_furn_before_a_continuing_noun_has_no_stop_but_before_a_new_sentence_it_has(self):
        self.assertEqual(E("fully furn. Choson/Kallah apt."), "fully furnished Choson/Kallah apartment.")
        self.assertEqual(E("Newer furnished/unfurn. Full kitchen."), "Newer furnished/unfurnished. Full kitchen.")

    def test_capitals_follow_the_original(self):
        self.assertEqual(E("Av. immediately."), "Available immediately.")
        self.assertEqual(E("Apt. is large."), "Apartment is large.")
        self.assertEqual(E("nice apt."), "nice apartment.")
        self.assertEqual(E("Kitchen. WD. Large."), "Kitchen. Washer/dryer. Large.")       # shouted initials: capital only at a sentence start
        self.assertEqual(E("Large EIK, WD."), "Large eat-in kitchen, washer/dryer.")

    def test_a_repeated_availability_is_printed_once(self):
        self.assertEqual(E("Close to Shuls. Av. Av. imm."), "Close to Shuls. Available immediately.")

    def test_choson_slash_spacing_is_tidied(self):
        self.assertEqual(E("Furnished Choson/ Kallah apt."), "Furnished Choson/Kallah apartment.")


class Punctuation(unittest.TestCase):
    def test_an_ellipsis_is_kept_whole(self):
        self.assertEqual(E("Use of kitchen, WD... Av. imm."), "Use of kitchen, washer/dryer... Available immediately.")

    def test_a_doubled_full_stop_is_tidied(self):
        self.assertEqual(E("master suite etc.."), "master suite etc.")

    def test_a_stray_space_before_a_comma_is_removed(self):
        self.assertEqual(E("Nice apt , big"), "Nice apartment, big")


class LeaveAlone(unittest.TestCase):
    def test_real_words_are_never_touched(self):
        for text in ("Available immediately.", "Furnished, unfurnished, minimum 3 months.", "Apartment with minyan nearby.",
                     "Finished basement, finished attic.", "Mon-Fri", "Duplex, upgraded, fully renovated.",
                     "Dec 1", "Shabbos", "Minyanim 5 minutes away."):
            self.assertEqual(E(text), text, text)

    def test_text_without_abbreviations_is_unchanged(self):
        t = "Beautiful colonial with finished basement, 2-car garage and a large backyard. Available immediately."
        self.assertEqual(E(t), t)

    def test_no_rule_runs_inside_a_longer_word(self):
        for t in ("immediately", "apartments", "furnished", "unfurnished", "backyard", "basement", "minimum", "feet", "private",
                  "upgraded", "through", "distance", "bedrooms", "stainless steel"):
            self.assertEqual(E(f"The {t}."), f"The {t}.", t)

    def test_names_and_other_all_caps_are_left_alone(self):
        self.assertEqual(E("Near BMG and the YU shul."), "Near BMG and the YU shul.")
        self.assertEqual(E("Call or text 732-555-0101."), "Call or text 732-555-0101.")

    def test_a_dashed_or_slashed_wd_is_not_confused_with_w_slash(self):
        self.assertEqual(E("W/D in unit; w/ pool"), "Washer/dryer in unit; with pool")       # a capital at the start of the text


class InTheParser(unittest.TestCase):
    def test_clean_comment_spells_out_abbreviations(self):
        self.assertEqual(P.clean_comment("Furn. apt. Av.imm. WD."), "Furnished apartment. Available immediately. Washer/dryer.")

    def test_glued_words_and_abbreviations_together(self):
        self.assertEqual(P.clean_comment("Beautifulfurnishedapt. Largewindows. Av.imm."),
                         "Beautiful furnished apartment. Large windows. Available immediately.")

    def test_a_long_spelled_out_description_is_not_cut_short(self):
        raw = " ".join(["Beautiful apt. with lg. bkyd. and priv. entrance."] * 6)
        self.assertGreater(len(P.clean_comment(raw)), 300)


if __name__ == "__main__":
    unittest.main()
