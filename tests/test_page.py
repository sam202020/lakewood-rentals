"""The page build.py writes: a complete HTML document, and listing text that cannot become part of it."""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import build  # noqa: E402
import week_data  # noqa: E402

HOSTILE = 'Nice apartment </script><img src=x onerror=alert(1)> <!-- <script> /*__SEARCH_CORE__*/'


def payload(page):
    return re.search(r'<script id="payload" type="application/json">(.*?)</script>', page, re.S).group(1)


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = week_data.week()
        cls.data["listings"][0]["comments"] = HOSTILE
        cls.data["listings"][0]["location"] = "</SCRIPT><b>x"
        cls.page = build.render_page(cls.data)

    def test_advertiser_text_cannot_close_the_data_block_or_add_markup(self):
        block = payload(self.page)
        self.assertNotIn("<", block)                       # no tag of any kind can start inside the data
        back = json.loads(block)
        self.assertEqual(back["listings"][0]["comments"], HOSTILE)      # and the text itself is unchanged
        self.assertEqual(back["count"], self.data["count"])
        self.assertNotIn("<img src=x", self.page)

    def test_it_is_a_complete_document_in_standards_mode_with_a_language_an_icon_and_a_heading(self):
        self.assertTrue(self.page.startswith('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">'))
        head, body = self.page.split("</head>", 1)
        self.assertIn('<link rel="icon" href="favicon.svg"', head)
        self.assertIn("<title>Lakewood NJ Area Rentals</title>", head)
        self.assertIn('rel="canonical"', head)
        self.assertIn("<body>", body)
        self.assertEqual(body.count('<h1 class="brand">'), 1)
        self.assertTrue(self.page.rstrip().endswith("</body>\n</html>"))
        self.assertNotIn("__BODY__", self.page)
        self.assertTrue((ROOT / "docs" / "favicon.svg").exists())


if __name__ == "__main__":
    unittest.main()
