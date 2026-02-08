"""
Tests for database models.
"""

from models import User, Channel, UserChannel, Product, PriceHistory


def test_create_user(db_session):
    user = User(id=1, user_id=12345, username="testuser")
    db_session.add(user)
    db_session.commit()

    result = db_session.get(User, 1)
    assert result.user_id == 12345
    assert result.username == "testuser"
    assert result.added_at is not None


def test_create_channel(db_session):
    channel = Channel(identifier="test_channel")
    db_session.add(channel)
    db_session.commit()

    result = db_session.query(Channel).filter_by(identifier="test_channel").one()
    assert result.identifier == "test_channel"
    assert result.added_at is not None


def test_user_channel_association(db_session):
    user = User(id=1, user_id=100, username="pippo")
    channel = Channel(identifier="offerte")
    db_session.add_all([user, channel])
    db_session.flush()

    link = UserChannel(user_id=user.user_id, channel_id=channel.id)
    db_session.add(link)
    db_session.commit()

    result = db_session.query(UserChannel).filter_by(user_id=100).first()
    assert result is not None
    assert result.channel_id == channel.id


def test_user_unique_constraint(db_session):
    user1 = User(id=1, user_id=100, username="pippo")
    user2 = User(id=2, user_id=100, username="pippo_dup")
    db_session.add(user1)
    db_session.commit()

    db_session.add(user2)
    try:
        db_session.commit()
        assert False, "Should fail due to duplicate user_id"
    except Exception:
        db_session.rollback()


def test_create_product_with_price(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="iphone 15", target_price=799.0)
    db_session.add(product)
    db_session.commit()

    result = db_session.query(Product).filter_by(user_id=100).one()
    assert result.name == "iphone 15"
    assert result.target_price == 799.0
    assert result.added_at is not None


def test_create_product_without_price(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="airpods", target_price=None)
    db_session.add(product)
    db_session.commit()

    result = db_session.query(Product).filter_by(name="airpods").one()
    assert result.target_price is None


def test_product_unique_per_user(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    db_session.add(Product(user_id=100, name="iphone 15", target_price=800.0))
    db_session.commit()

    db_session.add(Product(user_id=100, name="iphone 15", target_price=700.0))
    try:
        db_session.commit()
        assert False, "Should fail due to duplicate product"
    except Exception:
        db_session.rollback()


def test_same_product_different_users(db_session):
    """Two different users can monitor the same product."""
    user1 = User(id=1, user_id=100, username="pippo")
    user2 = User(id=2, user_id=200, username="pluto")
    db_session.add_all([user1, user2])
    db_session.flush()

    db_session.add(Product(user_id=100, name="iphone 15", target_price=800.0))
    db_session.add(Product(user_id=200, name="iphone 15", target_price=700.0))
    db_session.commit()

    products = db_session.query(Product).filter_by(name="iphone 15").all()
    assert len(products) == 2


def test_delete_product(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="airpods")
    db_session.add(product)
    db_session.commit()

    db_session.delete(product)
    db_session.commit()

    result = db_session.query(Product).filter_by(user_id=100).all()
    assert len(result) == 0


def test_multiple_products_per_user(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    db_session.add(Product(user_id=100, name="iphone 15", target_price=800.0))
    db_session.add(Product(user_id=100, name="airpods", target_price=None))
    db_session.add(Product(user_id=100, name="macbook pro", target_price=1500.0))
    db_session.commit()

    products = db_session.query(Product).filter_by(user_id=100).all()
    assert len(products) == 3


def test_user_paused_default(db_session):
    """New user has paused=False by default."""
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.commit()
    result = db_session.get(User, 1)
    assert result.paused is False


def test_user_pause_resume(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.commit()

    user.paused = True
    db_session.commit()
    assert db_session.get(User, 1).paused is True

    user.paused = False
    db_session.commit()
    assert db_session.get(User, 1).paused is False


def test_product_with_category(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="iphone 15", category="elettronica")
    db_session.add(product)
    db_session.commit()

    result = db_session.query(Product).filter_by(user_id=100).one()
    assert result.category == "elettronica"


def test_product_without_category(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="airpods")
    db_session.add(product)
    db_session.commit()

    result = db_session.query(Product).filter_by(user_id=100).one()
    assert result.category is None


def test_create_price_history(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="iphone 15", target_price=800.0)
    db_session.add(product)
    db_session.flush()

    entry = PriceHistory(
        product_id=product.id,
        user_id=100,
        price=749.0,
        channel="OfferteTest",
        message_text="iPhone 15 a 749",
        message_link="https://t.me/test/123",
        source="realtime",
    )
    db_session.add(entry)
    db_session.commit()

    result = db_session.query(PriceHistory).filter_by(user_id=100).one()
    assert result.price == 749.0
    assert result.channel == "OfferteTest"
    assert result.source == "realtime"
    assert result.message_link == "https://t.me/test/123"
    assert result.found_at is not None


def test_price_history_multiple_entries(db_session):
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.flush()

    product = Product(user_id=100, name="airpods")
    db_session.add(product)
    db_session.flush()

    db_session.add(PriceHistory(product_id=product.id, user_id=100, price=199.0, channel="Ch1", message_text="a"))
    db_session.add(PriceHistory(product_id=product.id, user_id=100, price=179.0, channel="Ch2", message_text="b"))
    db_session.add(PriceHistory(product_id=product.id, user_id=100, price=None, channel="Ch3", message_text="c", source="backfill"))
    db_session.commit()

    entries = db_session.query(PriceHistory).filter_by(product_id=product.id).all()
    assert len(entries) == 3
    backfill = [e for e in entries if e.source == "backfill"]
    assert len(backfill) == 1


def test_remove_user_channel_keeps_channel(db_session):
    """Removing a user-channel link does not delete the channel itself."""
    user = User(id=1, user_id=100, username="pippo")
    channel = Channel(identifier="offerte")
    db_session.add_all([user, channel])
    db_session.flush()

    link = UserChannel(user_id=100, channel_id=channel.id)
    db_session.add(link)
    db_session.commit()

    db_session.delete(link)
    db_session.commit()

    assert db_session.query(UserChannel).filter_by(user_id=100).first() is None
    assert db_session.query(Channel).filter_by(identifier="offerte").one() is not None


def test_remove_user_channel_other_users_unaffected(db_session):
    """Removing one user's channel link doesn't affect other users."""
    user1 = User(id=1, user_id=100, username="pippo")
    user2 = User(id=2, user_id=200, username="pluto")
    channel = Channel(identifier="offerte")
    db_session.add_all([user1, user2, channel])
    db_session.flush()

    db_session.add(UserChannel(user_id=100, channel_id=channel.id))
    db_session.add(UserChannel(user_id=200, channel_id=channel.id))
    db_session.commit()

    link = db_session.query(UserChannel).filter_by(user_id=100).first()
    db_session.delete(link)
    db_session.commit()

    assert db_session.query(UserChannel).filter_by(user_id=100).first() is None
    assert db_session.query(UserChannel).filter_by(user_id=200).first() is not None


def test_user_lang_code_default(db_session):
    """New user has lang_code='en' by default."""
    user = User(id=1, user_id=100, username="pippo")
    db_session.add(user)
    db_session.commit()
    result = db_session.get(User, 1)
    assert result.lang_code == "en"


def test_user_lang_code_custom(db_session):
    """User can be created with a custom lang_code."""
    user = User(id=1, user_id=100, username="pippo", lang_code="it")
    db_session.add(user)
    db_session.commit()
    result = db_session.get(User, 1)
    assert result.lang_code == "it"
