"""
Tests for product + price matching logic.
"""

from match_recorder import check_product_match
from models import Product, User


def _create_user_with_product(db_session, name, target_price=None):
    """Helper: create a user and a monitored product."""
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()
    product = Product(user_id=100, name=name, target_price=target_price)
    db_session.add(product)
    db_session.commit()
    return product


# --- Name matching ---

def test_product_name_found(db_session):
    product = _create_user_with_product(db_session, "iphone 15")
    result = check_product_match(product, "Nuovo iPhone 15 Pro in offerta a 899")
    assert result is not None


def test_product_name_not_found(db_session):
    product = _create_user_with_product(db_session, "iphone 15")
    result = check_product_match(product, "Samsung Galaxy S24 a 699")
    assert result is None


def test_product_name_case_insensitive(db_session):
    product = _create_user_with_product(db_session, "airpods")
    result = check_product_match(product, "AIRPODS Pro 2 disponibili!")
    assert result is not None


# --- Without target price ---

def test_no_target_matches_without_price_in_message(db_session):
    """Without target, matches even if message has no prices."""
    product = _create_user_with_product(db_session, "airpods")
    result = check_product_match(product, "AirPods Pro disponibili in negozio!")
    assert result is not None
    assert result["price_found"] is None


def test_no_target_matches_with_price_in_message(db_session):
    """Without target, matches even if message has a price."""
    product = _create_user_with_product(db_session, "airpods")
    result = check_product_match(product, "AirPods Pro a €199")
    assert result is not None
    assert result["price_found"] is None


# --- With target price ---

def test_price_below_target(db_session):
    product = _create_user_with_product(db_session, "iphone 15", target_price=800.0)
    result = check_product_match(product, "iPhone 15 a 749€ spedizione inclusa")
    assert result is not None
    assert result["price_found"] == 749.0


def test_price_exactly_at_target(db_session):
    """Price == target: should notify."""
    product = _create_user_with_product(db_session, "iphone 15", target_price=800.0)
    result = check_product_match(product, "iPhone 15 a €800")
    assert result is not None
    assert result["price_found"] == 800.0


def test_price_above_target(db_session):
    product = _create_user_with_product(db_session, "iphone 15", target_price=800.0)
    result = check_product_match(product, "iPhone 15 a €899")
    assert result is None


def test_no_price_in_message_with_target(db_session):
    """Product found but no price in message with target set: don't notify."""
    product = _create_user_with_product(db_session, "iphone 15", target_price=800.0)
    result = check_product_match(product, "iPhone 15 disponibile in negozio")
    assert result is None


def test_multiple_prices_uses_lowest(db_session):
    """With multiple prices, use the lowest for comparison."""
    product = _create_user_with_product(db_session, "iphone 15", target_price=500.0)
    result = check_product_match(product, "iPhone 15 da €899 a €499 in promo!")
    assert result is not None
    assert result["price_found"] == 499.0


# --- Edge cases ---

def test_empty_message(db_session):
    product = _create_user_with_product(db_session, "airpods")
    result = check_product_match(product, "")
    assert result is None


def test_product_name_as_substring(db_session):
    """'iphone' matches inside 'iphone 15 pro' (substring)."""
    product = _create_user_with_product(db_session, "iphone")
    result = check_product_match(product, "Nuovo iPhone 15 Pro a €999")
    assert result is not None


# --- Fuzzy matching ---

def test_fuzzy_match_with_hyphen(db_session):
    """'iphone 15' matches 'i-Phone 15'."""
    product = _create_user_with_product(db_session, "iphone 15")
    result = check_product_match(product, "Nuovo i-Phone 15 in offerta!")
    assert result is not None


def test_fuzzy_match_no_space(db_session):
    """'iphone 15' does NOT match 'iPhone15' (number attached)."""
    product = _create_user_with_product(db_session, "iphone 15")
    # "iPhone15" normalized -> "iphone15", "iphone 15" normalized -> "iphone 15"
    # No match because fuzzy removes hyphens/underscores but doesn't add spaces
    result = check_product_match(product, "iPhone15 a 799€")
    assert result is None


def test_fuzzy_match_extra_spaces(db_session):
    """'iphone 15' matches 'iPhone  15' (multiple spaces)."""
    product = _create_user_with_product(db_session, "iphone 15")
    result = check_product_match(product, "Nuovo iPhone  15 Pro a €899")
    assert result is not None


def test_fuzzy_match_underscore(db_session):
    """'airpods' matches 'Air_Pods' (underscore removed)."""
    product = _create_user_with_product(db_session, "airpods")
    result = check_product_match(product, "Air_Pods Pro 2 disponibili!")
    assert result is not None


# --- Names without keywords (#55) ---

def test_name_without_keywords_matches_nothing(db_session):
    product = _create_user_with_product(db_session, "")
    for name in ["", "  ", "-", "_ -", ".", "€!"]:
        product.name = name
        assert check_product_match(product, "Offerta: iPhone 15 a 749€! Link: amzn.eu/d/x") is None, repr(name)


def test_name_without_keywords_still_matches_by_link(db_session):
    product = _create_user_with_product(db_session, "")
    product.asin = "B0TEST1234"
    assert check_product_match(product, "offerta", {"B0TEST1234"}) is not None


# --- Posts listing several products (#72) ---

_MULTI_PRODUCT_POST = """🔈 SOUNDBAR + SUBWOOFER TCL 340W
📉 A 79,47€ invece di 93,49€
🛒 Sconto 14,02€ visibile in APP
🔗 https://tidd.ly/3VrLDKz

📞 BOSE QuietComfort auricolari
📉 A 93,46€ invece di 109,95€
🛒 Sconto 16,49€ visibile in APP
🔗 https://tidd.ly/4BUgkbI

🎧 BOSE QuietComfort cuffie
📉 A 161,46€ invece di 189,95€
🛒 Sconto 28,49€ visibile in APP
🔗 https://tidd.ly/3UWtBQi

🚛 MediaWorld - Offerta visibile solo in APP"""


def test_multi_product_post_uses_the_price_of_the_paragraph_naming_the_product(db_session):
    product = _create_user_with_product(db_session, "bose quietcomfort cuffie", target_price=200.0)
    result = check_product_match(product, _MULTI_PRODUCT_POST)
    assert result is not None
    assert result["price_found"] == 161.46


def test_multi_product_post_ignores_another_products_lower_price(db_session):
    product = _create_user_with_product(db_session, "bose quietcomfort cuffie", target_price=100.0)
    assert check_product_match(product, _MULTI_PRODUCT_POST) is None


def test_price_in_a_paragraph_without_the_name_still_counts(db_session):
    product = _create_user_with_product(db_session, "ninja blast", target_price=50.0)
    result = check_product_match(product, "🔥 Ninja Blast frullatore portatile\n\n📉 In offerta a 39,99€")
    assert result is not None
    assert result["price_found"] == 39.99
