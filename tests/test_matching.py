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
    assert check_product_match(product, "offerta https://amzn.eu/d/x", {"https://amzn.eu/d/x": "B0TEST1234"}) is not None


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


def test_price_in_a_paragraph_after_the_name_counts(db_session):
    """CouponsItalia: a banner, then the product, then its price."""
    product = _create_user_with_product(db_session, "fairy platinum", target_price=40.0)
    post = "😱DA NON PERDEREEE😱\n\n❗192 Caps Fairy Platinum Plus\n\n💰  PASSA DA 69,99€ A 36,99€\n👉  Apri Link Amazon"
    assert check_product_match(product, post)["price_found"] == 36.99


def test_variant_listed_under_the_only_price_takes_it(db_session):
    """pallok/82646: variants listed after the one price of the post."""
    product = _create_user_with_product(db_session, "orsetti d'oro", target_price=1.0)
    post = "Selezione Haribo\n\n🍬 Haribo Caramelle Gommose\n📉 In offerta a 0,99€\n\n🔗 Coccodrì\n🔗 Orsetti D'Oro\n\nDisclaimer #adv"
    assert check_product_match(product, post)["price_found"] == 0.99


def test_product_per_line_list_uses_the_price_on_the_products_line(db_session):
    """Issue #76, affaridanerd/37621: one product per line, no blank lines between them."""
    product = _create_user_with_product(db_session, "ocarina of time", target_price=100.0)
    post = (
        "🔴 Nintendo Switch 2\n\n"
        "🥇 The Legend of Zelda: Ocarina of Time - 69,00€\n"
        "🥈 Nintendo Switch Sports Resort - 59,90€\n"
        "🥉 Donkey Kong Bananza - 55,99€"
    )
    assert check_product_match(product, post)["price_found"] == 69.0


def test_name_line_face_value_with_the_price_below_keeps_both(db_session):
    """pallok/82717: the name line carries the card's face value, the next line the price."""
    product = _create_user_with_product(db_session, "playstation network card", target_price=70.0)
    post = "75€ di credito a 61€ da Eneba\n\n🎮 PlayStation Network Card 75€\n📉 In offerta a 60,96€"
    assert check_product_match(product, post)["price_found"] == 60.96


def test_blank_line_of_invisible_characters_separates_paragraphs(db_session):
    """Issue #76: a "blank" line made of Hangul fillers, zero-width characters or a Braille blank."""
    product = _create_user_with_product(db_session, "bose cuffie", target_price=200.0)
    for spacer in ["\u3164", "\u200b\u200d", "\u2800", "\uffa0", "\u115f"]:
        post = f"TCL soundbar\nA 79,47€\n{spacer}\nBOSE cuffie\nA 161,46€\n{spacer}\nFooter"
        assert check_product_match(product, post)["price_found"] == 161.46, ascii(spacer)


def test_link_only_match_in_multi_product_post_uses_the_linked_paragraph(db_session):
    """Issue #75: the product's name is not in the post, its link is."""
    product = _create_user_with_product(db_session, "cuffie noise cancelling", target_price=200.0)
    product.asin = "B0BOSE0001"
    post = _MULTI_PRODUCT_POST.replace("https://tidd.ly/3UWtBQi", "https://amzn.eu/d/bose")
    result = check_product_match(product, post, {"https://amzn.eu/d/bose": "B0BOSE0001", "https://tidd.ly/3VrLDKz": "B0TCL00001"})
    assert result["price_found"] == 161.46


def test_section_heading_takes_the_prices_below_it(db_session):
    """affaridanerd/37621: a heading names the product, its items follow; sections above are other products."""
    product = _create_user_with_product(db_session, "nintendo switch 2", target_price=100.0)
    post = "🔵 PlayStation 5\n\n🥇 Grand Theft Auto V - 19,99€\n\n🔴 Nintendo Switch 2\n\n🥇 Donkey Kong Bananza - 55,99€"
    assert check_product_match(product, post)["price_found"] == 55.99


def test_link_in_its_own_paragraph_takes_the_post_price(db_session):
    """pallok/82680: the link sits below its product's paragraph, a later paragraph quotes another amount."""
    product = _create_user_with_product(db_session, "sedia", target_price=40.0)
    product.name, product.asin = "", "B0SEDIA001"
    post = (
        "🪑 Sedia da Ufficio Ergonomica\n📉 In offerta a 34,02€\n\n🔗 https://tidd.ly/4e8ST4h\n\n"
        "👉 Qui altre offerte (PayPal da 45€ terminato)"
    )
    assert check_product_match(product, post, {"https://tidd.ly/4e8ST4h": "B0SEDIA001"})["price_found"] == 34.02


def test_two_product_list_without_blank_line_uses_the_products_line(db_session):
    """Issue #76: two lines, each a product with its price."""
    product = _create_user_with_product(db_session, "bose qc", target_price=200.0)
    assert check_product_match(product, "Bose QC 161€\nTCL soundbar 79€")["price_found"] == 161.0


def test_price_lines_under_a_priced_name_line_count(db_session):
    """One product: its name line with a price, then lines that only quote prices."""
    product = _create_user_with_product(db_session, "bose qc cuffie", target_price=170.0)
    post = "Bose QC cuffie a 199€\n🔥 Ora a 161,46€\n📉 Minimo storico 150€"
    assert check_product_match(product, post)["price_found"] == 150.0


def test_name_split_by_a_hidden_link_at_a_line_end_still_matches(db_session):
    """message_text puts a hidden link at the end of its line, inside a name that wraps."""
    product = _create_user_with_product(db_session, "bose quiet comfort", target_price=200.0)
    assert check_product_match(product, "Bose Quiet https://amzn.to/X\nComfort cuffie 161€")["price_found"] == 161.0


def test_link_is_matched_whole_and_case_sensitive(db_session):
    """Short links differ by one character or by case: another product's link is not this one's."""
    product = _create_user_with_product(db_session, "", target_price=200.0)
    product.asin = "B0BOSE0001"
    post = "TCL 79€\nhttps://amzn.to/abcd\n\nTCL bis 89€\nhttps://amzn.to/ABC\n\nBOSE 161€\nhttps://amzn.to/abc"
    asin_by_url = {"https://amzn.to/abc": "B0BOSE0001", "https://amzn.to/abcd": "B0TCL00001", "https://amzn.to/ABC": "B0TCL00002"}
    assert check_product_match(product, post, asin_by_url)["price_found"] == 161.0
