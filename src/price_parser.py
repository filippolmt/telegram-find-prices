"""
Extract prices from text (European/Italian formats).
"""

import math
import re

# Pattern for European price formats:
# €123 | 123€ | €123,50 | 123.50€ | EUR 123 | 123 euro | 1.234,56€ | 1.299.00€ | etc.
# A dot before exactly two digits is a decimal point ("15.57€"), before three a thousands separator.
# "euro" before "EUR": otherwise "20 euro di sconto" matches only "20 eur".
_PRICE_PATTERN = re.compile(
    r"""
    (?:€|euro|EUR)\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2}|\.\d{2}(?!\d))?)  # €1.234,56, €2.43 or EUR 123
    |
    (\d{1,3}(?:\.\d{3})*(?:,\d{1,2}|\.\d{2}(?!\d))?)\s*(?:€|euro|EUR)  # 1.234,56€, 15.57€ or 123 euro
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Line text right before an amount that makes it an amount off, not a price.
# Mid-line, "con coupon 39€" / "Codice sconto 39€" is the price paid, so most cases are anchored to the line start.
_DISCOUNT_PREFIX = re.compile(
    r"""
    (?:
        ^\W*(?:sconto|risparmi[oa]?|rimborso|cashback)[\s:\-]+(?:d[ia]\s+)?  # "🛒 Sconto 5,77€", "Rimborso di 50€"
        | ^\W*coupon\s+d[ia][\s:]+                         # "Coupon da 5€", "Coupon da: 5€" ("Coupon: 39€" is the price)
        | \bapplica\s+(?:il\s+)?coupon[\s:]+(?:d[ia]\s+)?  # "Applica il coupon da 2,92€"
        | \bspesa\s+minima\s+di\s+                         # "spesa minima di 35€"
        | \(\s*sconto[\s:\-]+(?:di\s+)?                     # "(sconto 10€)"
        | ^\W*al\s+supermercato\b.*                         # "Al supermercato costa 4,37€. QUI SOLO 3,12€" (unit prices)
        | ^\W*qui\s+su\s+amazon\b.*                         # the same comparison wrapped onto a second line
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Text right after an amount that makes it an amount off, money back or a per-use price:
# "1€ dal minimo", "10€ di sconto", "50€ di rimborso", "200 euro in meno", "0,07€ per lavaggio", "0,07€/lavaggio".
_DISCOUNT_SUFFIX = re.compile(
    r"\s*(?:dal\s+(?:prezzo\s+)?minimo|di\s+(?:sconto|coupon|ribasso|rimborso|cashback)|in\s+meno|(?:per\s+|/\s*)(?:lavaggio|bustina))\b",
    re.IGNORECASE,
)


def _is_discount(text: str, match: re.Match) -> bool:
    line_before = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
    return bool(_DISCOUNT_PREFIX.search(line_before) or _DISCOUNT_SUFFIX.match(text, match.end()))


# Words of a line that only quotes a price ("📉 In offerta a 39€", "💶 Prezzo precedente 49€"), not a product.
_PRICE_ONLY_WORDS = frozenset(
    "a al da di il in con e ora solo scende passa invece offerta minimo storico prezzo precedente attuale finale"
    " scontato applicando coupon codice media giorni".split()
)


def is_price_only(line: str) -> bool:
    """Whether the text before a line's first price only quotes it, naming no product."""
    match = _PRICE_PATTERN.search(line)
    words = re.findall(r"[^\W\d_]+", line[: match.start()] if match else line)
    return all(word.lower() in _PRICE_ONLY_WORDS for word in words)


def _to_float(raw: str) -> float:
    """Convert '1.234,56' -> 1234.56, '15.57' -> 15.57"""
    if re.search(r"\.\d{2}$", raw):
        raw = raw[:-3] + "," + raw[-2:]
    return float(raw.replace(".", "").replace(",", "."))


def extract_prices(text: str) -> list[float]:
    """Return all prices found in text as floats."""
    prices = []
    for match in _PRICE_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw and not _is_discount(text, match):
            prices.append(_to_float(raw))
    return prices


_CURRENCY_RE = re.compile(r"€|euro?", re.IGNORECASE)


def parse_target_price(text: str) -> float | None:
    """Parse a user-typed target price ('49,90', '€ 49', '49 EUR'); None if invalid."""
    cleaned = _CURRENCY_RE.sub("", text).replace(",", ".").strip()
    try:
        price = float(cleaned)
    except ValueError:
        return None
    return price if math.isfinite(price) and price >= 0 else None
