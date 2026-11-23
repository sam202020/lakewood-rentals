"""Put the spaces back into words the PDF ran together.

The PDF's text layer drops the space characters in some rows ("Beautifulnewtopoftheline furnished.
Great locationneareverything."). The character positions don't show where the spaces were, so the only
way back is a word list: split a token into known words with the fewest, most common pieces.

Conservative on purpose - a wrong split is worse than a run-together word:
  * a token that is itself a known word is never touched;
  * a token is split only if EVERY piece is a known word (no unknown leftovers);
  * pieces shorter than 3 letters must be from a small list of real short words (of, in, to, ...).
The vocabulary is data/words_core.txt (hand-maintained, most common first) followed by
data/words_corpus.txt (words from past descriptions that are real English words).
"""
import functools
import math
import pathlib
import re

DATA = pathlib.Path(__file__).parent / "data"
SHORT_OK = {"a", "an", "in", "on", "of", "to", "or", "at", "as", "by", "if", "it", "no", "up", "us", "we", "is",
            "be", "do", "so", "my", "me", "he", "av", "mo", "sf", "ft", "sq", "tv", "bd", "br", "ba", "wd", "ac", "w"}
MAX_PIECES = 10


@functools.lru_cache(maxsize=1)
def vocabulary():
    """{word: cost}; earlier in the files = more common = cheaper."""
    words = []
    for name in ("words_core.txt", "words_corpus.txt"):
        f = DATA / name
        if f.exists():
            for line in f.read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    words.extend(w.lower() for w in line.split())
    cost = {}
    for rank, w in enumerate(words):
        if w not in cost:
            cost[w] = math.log(rank + 2)
    return cost


def split_token(token):
    """['beautiful', 'new', 'top'] for 'beautifulnewtop', or None when it should be left alone."""
    vocab = vocabulary()
    low = token.lower()
    if low in vocab or len(low) < 6:
        return None
    n = len(low)
    INF = float("inf")
    best = [(INF, 0, None)] * (n + 1)          # (cost, pieces, split point)
    best[0] = (0.0, 0, None)
    for i in range(1, n + 1):
        for j in range(max(0, i - 24), i):
            piece = low[j:i]
            if piece not in vocab or (len(piece) < 3 and piece not in SHORT_OK):
                continue
            if piece == "a" and (j == 0 or i == n):          # "a" only between two other words
                continue
            if piece == "w" and i != n:                      # "w" (with) only at the end: "furnished house w"
                continue
            c, k, _ = best[j]
            if c == INF or k + 1 > MAX_PIECES:
                continue
            cand = c + vocab[piece] + 0.6        # a little per-piece cost so fewer, longer words win
            if cand < best[i][0]:
                best[i] = (cand, k + 1, j)
    if best[n][0] == INF or best[n][1] < 2:
        return None
    out, i = [], n
    while i > 0:
        j = best[i][2]
        out.append(token[j:i])
        i = j
    return out[::-1]


def fix_glued(text):
    """Split every run-together word in `text`; everything else is left exactly as it was."""
    def one(m):
        parts = split_token(m.group())
        return " ".join(parts) if parts else m.group()
    return re.sub(r"[A-Za-z]{6,}", one, text)


def join_hyphenated(text):
    """Re-join a word the PDF broke across two lines: "environ- ment" -> "environment", "learn- ing" -> "learning".
    Left alone when both halves are real words ("well- kept")."""
    vocab = vocabulary()

    def one(m):
        left, right = m.group(1), m.group(2)
        if left.lower() in vocab and right.lower() in vocab and (left + right).lower() not in vocab:
            return m.group(0)
        return left + right
    return re.sub(r"\b([A-Za-z]{2,})- ([a-z]{2,})\b", one, text)
