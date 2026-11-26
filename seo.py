"""What search engines and link previews are told about the site.

build.py puts head_tags() into the page and writes sitemap.xml and robots.txt next to it.
The share image docs/og.png is a fixed picture made by tools/build_og_image.py (no date in it,
so it does not change every week).
"""
import datetime
import html
import re

SITE_URL = "https://lakewoodnjrentals.com/"        # must match docs/CNAME (tested)
SITE_NAME = "Lakewood NJ Area Rentals"
SHARE_TITLE = "Lakewood NJ Area Rentals: apartments, houses and rooms"
IMAGE_URL = SITE_URL + "og.png"
IMAGE_ALT = "Lakewood NJ Area Rentals. Search by neighborhood, street or shul."

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def iso_date(list_date):
    """'Wednesday, Nov. 25, 2026' -> '2026-11-25'; None when it can't be read."""
    m = re.search(r"([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})", list_date or "")
    if not m or m.group(1)[:3].lower() not in _MONTHS:
        return None
    try:
        return datetime.date(int(m.group(3)), _MONTHS.index(m.group(1)[:3].lower()) + 1, int(m.group(2))).isoformat()
    except ValueError:
        return None


def description(count, list_date):
    updated = f" Updated {list_date}." if list_date else ""
    return (f"{count} apartments, houses and rooms for rent in and around Lakewood, NJ. "
            f"Search by neighborhood, street or shul.{updated}")


def head_tags(count, list_date):
    """The <meta>/<link> lines for the page head."""
    text = description(count, list_date)
    tags = [
        ("name", "description", text),
        ("property", "og:type", "website"),
        ("property", "og:site_name", SITE_NAME),
        ("property", "og:title", SHARE_TITLE),
        ("property", "og:description", text),
        ("property", "og:url", SITE_URL),
        ("property", "og:locale", "en_US"),
        ("property", "og:image", IMAGE_URL),
        ("property", "og:image:type", "image/png"),
        ("property", "og:image:width", "1200"),
        ("property", "og:image:height", "630"),
        ("property", "og:image:alt", IMAGE_ALT),
        ("name", "twitter:card", "summary_large_image"),
        ("name", "twitter:title", SHARE_TITLE),
        ("name", "twitter:description", text),
        ("name", "twitter:image", IMAGE_URL),
    ]
    lines = [f'<link rel="canonical" href="{SITE_URL}">']
    lines += [f'<meta {kind}="{key}" content="{html.escape(value, quote=True)}">' for kind, key, value in tags]
    return "\n".join(lines)


def sitemap(list_date):
    """One page for now. lastmod is the date of the rental list, so it moves only when the listings do."""
    day = iso_date(list_date)
    lastmod = f"<lastmod>{day}</lastmod>" if day else ""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"  <url><loc>{SITE_URL}</loc>{lastmod}</url>\n"
            "</urlset>\n")


def robots():
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n"
