"""The page data for a frozen week (tests/fixtures/week.json), made with the current code and curated files.

Tests that need real listings use this, never listings.json or docs/index.html: those change every Wednesday, and a test
that depends on them passes one week and blocks the weekly refresh the next. Run as a script it prints the data as JSON
(the Node tests read that).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402
import geo  # noqa: E402

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "week.json"


def week():
    saved = json.loads(FIXTURE.read_text())
    listings = saved["listings"]
    places = geo.load_places()
    centers = build.locate(listings, places)
    return build.make_data(listings, saved["list_date"], places, centers, saved["neighborhoods_seen"])


if __name__ == "__main__":
    json.dump(week(), sys.stdout, ensure_ascii=False)
