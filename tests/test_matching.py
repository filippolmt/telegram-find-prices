"""
Tests for product + price matching logic.
"""

from models import User, Product
from channel_listener import check_product_match


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
