"""
Extract prices from text (European/Italian formats).
"""

import math
import re

# Pattern for European price formats:
# €123 | 123€ | €123,50 | 123.50€ | EUR 123 | 123 euro | 1.234,56€ | etc.
_PRICE_PATTERN = re.compile(
    r"""
    (?:€|EUR|euro)\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)  # €1.234,56 or EUR 123
    |
    (\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?)\s*(?:€|EUR|euro)  # 1.234,56€ or 123 euro
    """,
    re.IGNORECASE | re.VERBOSE,
)


# A discount, not a price: a line opening with "Sconto 5€" (mid-line, "con coupon 39€" is the price paid),
# or an amount followed by "dal minimo" / "di sconto".
_DISCOUNT_BEFORE = re.compile(r"^[^\w]*(?:sconto|coupon)[\s:\-]+(?:d[ia]\s+)?$", re.IGNORECASE)
_DISCOUNT_AFTER = re.compile(r"\s*(?:dal\s+minimo|di\s+(?:sconto|coupon))\b", re.IGNORECASE)


def _to_float(raw: str) -> float:
    """Convert '1.234,56' -> 1234.56"""
    return float(raw.replace(".", "").replace(",", "."))


def extract_prices(text: str) -> list[float]:
    """Return all prices found in text as floats."""
    prices = []
    for match in _PRICE_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        before = text[text.rfind("\n", 0, match.start()) + 1 : match.start()]
        if raw and not _DISCOUNT_BEFORE.search(before) and not _DISCOUNT_AFTER.match(text, match.end()):
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
