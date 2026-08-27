#!/usr/bin/env python3
"""Build the static Lakewood Rentals site.

  python3 build.py            # fetch live PDF, parse, write site/index.html
  python3 build.py --pdf X    # use a local PDF file instead of fetching

Safety: if parsing yields fewer than MIN_LISTINGS, the previous listings.json
is kept and the build aborts, so a bad fetch never wipes a good site.
"""
import argparse, json, pathlib, sys, datetime

import parse as P

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "listings.json"
TEMPLATE = ROOT / "site" / "template.html"
OUT = ROOT / "site" / "index.html"
MIN_LISTINGS = 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="local PDF path (default: fetch live)")
    args = ap.parse_args()

    src = args.pdf or P.SOURCE_URL
    list_date, listings = P.parse(P.fetch_pdf(src))

    if len(listings) < MIN_LISTINGS:
        print(f"ABORT: only {len(listings)} listings parsed (< {MIN_LISTINGS}). "
              f"Keeping existing data.", file=sys.stderr)
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
        "/*__DATA__*/null",
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
    )
    OUT.write_text(html)
    print(f"built {OUT}  ({len(listings)} listings, list_date={list_date!r})")


if __name__ == "__main__":
    main()
