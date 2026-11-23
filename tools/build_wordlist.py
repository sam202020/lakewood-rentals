#!/usr/bin/env python3
"""Rebuild data/words_corpus.txt: the real English words used in past descriptions, most common first.

  python3 tools/build_wordlist.py

Takes every word in listings.json comments that is also an ordinary dictionary word (/usr/share/dict/words),
so words that only exist because the PDF glued two together ("shortterm") are never learned as words.
Run it locally when new vocabulary shows up; the weekly routine does not need the dictionary because the
result is checked in. Hand-picked words and names belong in data/words_core.txt instead.
"""
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DICT = pathlib.Path("/usr/share/dict/words")


def main():
    if not DICT.exists():
        raise SystemExit("no /usr/share/dict/words on this machine")
    english = {w.strip().lower() for w in DICT.read_text(errors="ignore").splitlines() if w.strip().isalpha()}
    core = {w.lower() for line in (ROOT / "data" / "words_core.txt").read_text().splitlines()
            if line.strip() and not line.startswith("#") for w in line.split()}
    cnt = collections.Counter()
    for x in json.loads((ROOT / "listings.json").read_text())["listings"]:
        for t in re.findall(r"[A-Za-z]+", x.get("comments", "")):
            t = t.lower()
            if len(t) >= 3 and t in english and t not in core:
                cnt[t] += 1
    words = [w for w, _ in cnt.most_common()]
    (ROOT / "data" / "words_corpus.txt").write_text(
        "# Real English words from past descriptions (tools/build_wordlist.py), most common first.\n"
        + "\n".join(" ".join(words[i:i + 12]) for i in range(0, len(words), 12)) + "\n")
    print(f"{len(words)} words -> data/words_corpus.txt")


if __name__ == "__main__":
    main()
