"""What search engines and link previews are told (seo.py, and the files in docs/)."""
import pathlib
import struct
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import seo  # noqa: E402


class SeoText(unittest.TestCase):
    def test_site_url_is_the_custom_domain(self):
        self.assertEqual(seo.SITE_URL, "https://" + (ROOT / "docs" / "CNAME").read_text().strip() + "/")

    def test_list_date_becomes_an_iso_date(self):
        self.assertEqual(seo.iso_date("Wednesday, Nov. 25, 2026"), "2026-11-25")
        self.assertEqual(seo.iso_date("Wednesday, Sept. 2, 2026"), "2026-09-02")
        self.assertEqual(seo.iso_date("Wednesday, March 3, 2027"), "2027-03-03")
        self.assertIsNone(seo.iso_date("this week"))
        self.assertIsNone(seo.iso_date(None))

    def test_head_tags_carry_count_date_canonical_and_picture(self):
        tags = seo.head_tags(236, "Wednesday, Nov. 25, 2026")
        self.assertIn('<link rel="canonical" href="https://lakewoodnjrentals.com/">', tags)
        self.assertIn('<meta name="description" content="236 apartments', tags)
        self.assertIn("Updated Wednesday, Nov. 25, 2026.", tags)
        self.assertIn('<meta property="og:image" content="https://lakewoodnjrentals.com/og.png">', tags)

    def test_text_from_the_pdf_cannot_break_out_of_a_tag(self):
        self.assertNotIn('"><script>', seo.head_tags(1, '"><script>'))

    def test_sitemap_and_robots(self):
        self.assertIn("<loc>https://lakewoodnjrentals.com/</loc><lastmod>2026-11-25</lastmod>",
                      seo.sitemap("Wednesday, Nov. 25, 2026"))
        self.assertNotIn("lastmod", seo.sitemap(""))
        self.assertIn("Sitemap: https://lakewoodnjrentals.com/sitemap.xml", seo.robots())


class SeoFiles(unittest.TestCase):
    def test_built_page_has_the_tags(self):
        page = (ROOT / "docs" / "index.html").read_text()
        self.assertNotIn("__SEO__", page)
        self.assertEqual(page.count('rel="canonical"'), 1)
        self.assertIn('property="og:image"', page)

    def test_share_picture_is_1200_by_630_and_small(self):
        raw = (ROOT / "docs" / "og.png").read_bytes()
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", raw[16:24]), (1200, 630))
        self.assertLess(len(raw), 300_000)          # chat apps skip big preview pictures


if __name__ == "__main__":
    unittest.main()
