"""Values that look like personal data, in what a document's Markdown shows: email addresses, IBANs (by their
mod-97 check) and card numbers (by Luhn's). Counted per column or page, and named in a warning; never shown, and
never masked: the BA decides what may be committed."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
CARD = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
WORDS = {"email": ("email address", "email addresses"), "iban": ("IBAN", "IBANs"),
         "card": ("card number", "card numbers")}


def count(text: str) -> Counter:
    return Counter({"email": len(EMAIL.findall(text)),
                    "iban": sum(_iban(m.group(0)) for m in IBAN.finditer(text)),
                    "card": sum(_luhn(m.group(0)) for m in CARD.finditer(text))})


def warning(place: str, texts: Iterable[str]) -> str | None:
    """A warning naming the place and how many of each it holds, or None when it holds none."""
    found = Counter()
    for text in texts:
        found.update(count(text))
    parts = [f"{n} {WORDS[key][n != 1]}" for key in WORDS if (n := found[key])]
    if not parts:
        return None
    return f"{place} has values that look like personal data ({', '.join(parts)}): check before committing it"


def _iban(candidate: str) -> bool:
    # the last group may be the next word, in capitals: try without it too
    for text in (candidate, candidate.rsplit(" ", 1)[0]):
        compact = text.replace(" ", "")
        if 15 <= len(compact) <= 34:
            digits = "".join(str(int(c, 36)) for c in compact[4:] + compact[:4])
            if int(digits) % 97 == 1:
                return True
    return False


def _luhn(candidate: str) -> bool:
    digits = [int(d) for d in candidate if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0
