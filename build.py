#!/usr/bin/env python3
"""Build the static Lakewood NJ Area Rentals site.

  python3 build.py            # fetch live PDF, parse, write docs/index.html
  python3 build.py --pdf X    # use a local PDF file instead of fetching

Safety: the parsed listings go through checks.py before anything is written.
If a hard check fails (count collapsed, locations/phones missing, ...) the
build aborts with exit code 1 and leaves listings.json and docs/index.html
untouched, so a PDF layout change never replaces a good site with a bad one.
Soft problems are printed as WARN lines; the build still succeeds.
"""
import argparse, json, pathlib, sys, datetime

import checks
import parse as P

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "listings.json"
TEMPLATE = ROOT / "site" / "template.html"
SEARCH_CORE = ROOT / "site" / "search-core.js"
OUT = ROOT / "docs" / "index.html"


def previous_count():
    try:
        return json.loads(DATA.read_text()).get("count")
    except (OSError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="local PDF path (default: fetch live)")
    args = ap.parse_args()

    src = args.pdf or P.SOURCE_URL
    list_date, listings = P.parse(P.fetch_pdf(src))

    errors, warnings = checks.check(listings, previous_count())
    for w in warnings:
        print(f"WARN: {w}")
    if errors:
        for e in errors:
            print(f"ABORT: {e}", file=sys.stderr)
        print("Keeping existing listings.json and docs/index.html unchanged.", file=sys.stderr)
        sys.exit(1)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "list_date": list_date,
        "source_url": P.SOURCE_URL,
        "source_site": "https://masaumatan.com",
        "count": len(listings),
        "listings": listings,
    }
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    html = TEMPLATE.read_text().replace(
        "/*__SEARCH_CORE__*/", SEARCH_CORE.read_text()
    ).replace(
        "/*__DATA__*/null",
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )
    OUT.write_text(html)
    print(f"built {OUT}  ({len(listings)} listings, list_date={list_date!r}, "
          f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''})")


if __name__ == "__main__":
    main()
