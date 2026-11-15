"""
Extract prices from text (European/Italian formats).
"""

import math
import re

# Pattern for European price formats:
# €123 | 123€ | €123,50 | 123.50€ | EUR 123 | 123 euro | 1.234,56€ | etc.
# "euro" before "EUR": otherwise "20 euro di sconto" matches only "20 eur".
_PRICE_PATTERN = re.compile(
    r"""
    (?:€|euro|EUR)\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)  # €1.234,56 or EUR 123
    |
    (\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:€|euro|EUR)  # 1.234,56€ or 123 euro
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Line text right before an amount that makes it an amount off, not a price.
# Mid-line, "con coupon 39€" / "Codice sconto 39€" is the price paid, so most cases are anchored to the line start.
_DISCOUNT_PREFIX = re.compile(
    r"""
    (?:
        ^\W*(?:sconto|risparmi[oa]?)[\s:\-]+(?:d[ia]\s+)?   # "🛒 Sconto 5,77€", "Risparmi 18,23€"
        | ^\W*coupon\s+d[ia]\s+                            # "Coupon da 5€" ("Coupon: 39€" is the price)
        | \bapplica\s+(?:il\s+)?coupon[\s:]+(?:d[ia]\s+)?  # "Applica il coupon da 2,92€"
        | \bspesa\s+minima\s+di\s+                         # "spesa minima di 35€"
        | \(\s*sconto[\s:\-]+(?:di\s+)?                     # "(sconto 10€)"
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)
# Text right after an amount that makes it an amount off: "1€ dal minimo", "10€ di sconto", "200 euro in meno".
_DISCOUNT_SUFFIX = re.compile(r"\s*(?:dal\s+(?:prezzo\s+)?minimo|di\s+(?:sconto|coupon)|in\s+meno)\b", re.IGNORECASE)


def _is_discount(text: str, match: re.Match) -> bool:
    line_before = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
    return bool(_DISCOUNT_PREFIX.search(line_before) or _DISCOUNT_SUFFIX.match(text, match.end()))


def _to_float(raw: str) -> float:
    """Convert '1.234,56' -> 1234.56"""
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
