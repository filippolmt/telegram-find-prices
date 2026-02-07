"""
Extract prices from text (European/Italian formats).
"""

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


def _to_float(raw: str) -> float:
    """Convert '1.234,56' -> 1234.56"""
    return float(raw.replace(".", "").replace(",", "."))


def extract_prices(text: str) -> list[float]:
    """Return all prices found in text as floats."""
    prices = []
    for match in _PRICE_PATTERN.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            prices.append(_to_float(raw))
    return prices
