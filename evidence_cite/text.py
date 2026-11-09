from __future__ import annotations

import unicodedata

# Letters an OCR pass swaps for digits, lowercase. Folding maps them to the digit.
FOLD = {"o": "0", "l": "1", "i": "1", "|": "1", "s": "5", "b": "8", "z": "2"}


def _clusters(text: str):
    """(start, end, substring) of each base character with the combining marks that follow it."""
    start = 0
    for i in range(1, len(text) + 1):
        if i == len(text) or not unicodedata.combining(text[i]):
            yield start, i, text[start:i]
            start = i


def _normalise(text: str, fold: bool) -> tuple[str, list[int], list[int]]:
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for start, end, cluster in _clusters(text):
        for c in unicodedata.normalize("NFKC", cluster).casefold():
            if c.isspace():
                if out and out[-1] != " ":
                    out.append(" ")
                    starts.append(start)
                    ends.append(end)
                continue
            if fold:
                c = FOLD.get(c, c)
            out.append(c)
            starts.append(start)
            ends.append(end)
    if out and out[-1] == " ":
        out.pop()
        starts.pop()
        ends.pop()
    return "".join(out), starts, ends


def normalise(text: str, fold: bool = False) -> tuple[str, list[int]]:
    """Casefold, NFKC and collapse whitespace; with fold, also map OCR look-alikes to digits.

    Returns the new string and, for each of its characters, the offset in `text` where the
    character it came from starts (a base character and its combining marks count as one).
    """
    out, starts, _ = _normalise(text, fold)
    return out, starts


def locate(page: str, quote: str, fold: bool = False) -> tuple[int, int] | None:
    """Span (start, end) in `page` of the first place `quote` occurs, or None."""
    p, starts, ends = _normalise(page, fold)
    q, _, _ = _normalise(quote, fold)
    if not q:
        return None
    pos = p.find(q)
    if pos < 0:
        return None
    return starts[pos], ends[pos + len(q) - 1]
