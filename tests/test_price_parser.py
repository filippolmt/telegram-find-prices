"""
Tests for price parser.
"""

import pytest

from price_parser import extract_prices, parse_target_price


def test_euro_symbol_before():
    assert extract_prices("Costa €799") == [799.0]


def test_euro_symbol_after():
    assert extract_prices("799€ spedizione inclusa") == [799.0]


def test_decimals_comma():
    assert extract_prices("Prezzo: 49,99€") == [49.99]


def test_thousands_separator():
    assert extract_prices("Solo 1.234,56€") == [1234.56]


def test_eur_keyword():
    assert extract_prices("EUR 100") == [100.0]


def test_euro_word():
    assert extract_prices("costa 50 euro") == [50.0]


def test_euro_word_case_insensitive():
    assert extract_prices("Solo 25 Euro!!!") == [25.0]


def test_multiple_prices():
    prices = extract_prices("Da €299 a €499")
    assert prices == [299.0, 499.0]


def test_no_price():
    assert extract_prices("Nessun prezzo qui") == []


def test_mixed_formats():
    prices = extract_prices("€10,50 oppure 20 euro")
    assert prices == [10.50, 20.0]


def test_thousands_only_no_decimals():
    assert extract_prices("Costa 1.234€") == [1234.0]


def test_space_before_euro_symbol():
    assert extract_prices("Solo 799 €") == [799.0]


def test_empty_string():
    assert extract_prices("") == []


def test_number_without_currency_not_matched():
    """Numbers without currency symbol should not be extracted."""
    assert extract_prices("Ho comprato 3 mele e 2 arance") == []


def test_large_price():
    assert extract_prices("€12.999,99") == [12999.99]


def test_single_digit_price():
    assert extract_prices("Solo €5") == [5.0]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("49.90", 49.90),
        ("49,90", 49.90),
        ("€ 49", 49.0),
        ("49€", 49.0),
        ("49 EUR", 49.0),
        ("49 eur", 49.0),
        ("49 euro", 49.0),
        ("49EUR", 49.0),
        ("49euro", 49.0),
        ("abc", None),
        ("", None),
        ("nan", None),
        ("inf", None),
        ("-5", None),
    ],
)
def test_parse_target_price(text, expected):
    assert parse_target_price(text) == expected


def test_distance_from_historical_low_is_not_a_price():
    """Issue #56: '1€ dal minimo' is how far the price is from the low, not the price."""
    assert extract_prices("Ninja Blast a 1€ dal minimo\n📉 In offerta a 39,99€") == [39.99]


@pytest.mark.parametrize(
    "line",
    [
        "Prodotti inclusi di 50€ di coupon",
        "Subito 10€ di sconto",
        "🛒 Sconto 5,77€ visibile in APP",
        "Sconto: 5€",
        "🛒 Sconto -5€",
        "Coupon da 5€",
        "Coupon di 5€",
        "Risparmi 250,00€ con 👉 @scontitoday",
        "Risparmio 10€",
        "Risparmia 5€",
        "Prezzo pieno (sconto 10€)",
        "- 10€ dal prezzo minimo",
        "Apple Watch Series 12 in titanio oro con 200 euro di sconto",
        "Il nuovo Studio Display di Apple costa 200 euro in meno su Amazon",
        "✅ Applica il coupon da 2,92€ al check out per ottenere questo prezzo!",
        'Clicca su "Applica coupon 10€" subito sotto al prezzo!',
        "🎁 Ottieni un omaggio con una spesa minima di 35€",
    ],
)
def test_amount_off_is_not_a_price(line):
    """Discounts, coupons, savings and minimum spends, mostly lines from real channels."""
    assert extract_prices(f"💰 Scende a 649,90€ da 899,90€\n{line}") == [649.90, 899.90]


@pytest.mark.parametrize(
    "line, prices",
    [
        ("Prezzo scontato 39€", [39.0]),
        ("Prezzo con coupon 39,99€", [39.99]),
        ("con lo sconto 39€", [39.0]),
        ("Codice sconto 39€", [39.0]),
        ("Coupon: 39,99€", [39.99]),
        ("Coupon 39,99€ invece di 49€", [39.99, 49.0]),
    ],
)
def test_price_paid_with_coupon_or_discount_is_a_price(line, prices):
    """Mid-line, or "Coupon" without "di"/"da", the amount is the price paid."""
    assert extract_prices(line) == prices
