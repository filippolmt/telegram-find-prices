"""
Tests for price parser.
"""

from price_parser import extract_prices


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
