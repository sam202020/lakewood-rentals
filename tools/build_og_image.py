#!/usr/bin/env python3
"""Draw docs/og.png, the 1200x630 picture shown when the site's link is shared (WhatsApp, etc.).

Run locally on a Mac after changing the wording:  python3 tools/build_og_image.py
The weekly routine does not run this; the picture is committed. Needs Pillow (installed with pdfplumber).
The words stay in the middle because some apps crop the preview to a square.
"""
import pathlib

from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "og.png"
FONTS = pathlib.Path("/System/Library/Fonts/Supplemental")
W, H = 1200, 630
GREEN, PALE, WHITE = (30, 92, 63), (205, 227, 214), (255, 255, 255)


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def main():
    img = Image.new("RGB", (W, H), GREEN)
    d = ImageDraw.Draw(img)

    def centered(text, y, f, fill):
        d.text((W / 2, y), text, font=f, fill=fill, anchor="mm")

    # a map pin above the name
    d.ellipse((570, 70, 630, 130), fill=WHITE)
    d.polygon([(578, 118), (622, 118), (600, 160)], fill=WHITE)
    d.ellipse((588, 88, 612, 112), fill=GREEN)

    big = font("Arial Bold.ttf", 84)
    centered("Lakewood NJ", 232, big, WHITE)
    centered("Area Rentals", 328, big, WHITE)
    centered("Apartments, houses and rooms", 428, font("Arial.ttf", 40), PALE)
    centered("Search by neighborhood, street or shul", 480, font("Arial.ttf", 40), PALE)
    centered("lakewoodnjrentals.com", 566, font("Arial Bold.ttf", 34), WHITE)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
