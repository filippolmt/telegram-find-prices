"""
Bot command handlers for Telegram bot interactions.
"""

import logging
import re

log = logging.getLogger(__name__)
from typing import Optional
from asyncio import TimeoutError as AsyncTimeoutError
from telethon import events, TelegramClient
from sqlalchemy.orm import Session, sessionmaker
from client_commands import ClientCommands
from config import Config
from models import User, Product, PriceHistory, UserChannel, Channel
from translations import t, resolve_lang, DEFAULT_LANGUAGE

_CHANNEL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$")
_INVITE_HASH_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_CANCEL_KEYWORDS = {"/cancel", "cancel", "/annulla", "annulla"}
_SKIP_KEYWORDS = {"/skip", "skip", "/salta", "salta"}


class BotCommands:
    """Telegram bot command handlers."""

    def __init__(
        self,
        bot_client: TelegramClient,
        client_commands: ClientCommands,
        db_session_factory: sessionmaker,
    ):
        self.bot_client = bot_client
        self.client_commands = client_commands
        self._session_factory = db_session_factory
        self._allowed_users = Config.ALLOWED_USERS

    def _is_authorized(self, user_id: int | None) -> bool:
        """Check if user is authorized. If ALLOWED_USERS is empty, everyone is allowed."""
        if not self._allowed_users:
            return True
        return user_id in self._allowed_users

    async def register_user_if_not_exists(self, event: events.NewMessage.Event) -> tuple[Optional[str], Optional[int], str, bool]:
        """Register the sender if not already registered.

        Returns: (username, user_id, lang, created)
        """
        sender = await event.get_sender()
        user_id: Optional[int] = getattr(event, "sender_id", None)
        username: Optional[str] = getattr(sender, "username", None)
        sender_lang = resolve_lang(getattr(sender, "lang_code", None))

        if user_id is None or username is None:
            return None, None, DEFAULT_LANGUAGE, False

        with self._session_factory() as session:
            existing = session.get(User, user_id)
            if existing is None:
                session.add(User(id=user_id, user_id=user_id, username=username, lang_code=sender_lang))
                session.commit()
                return username, user_id, sender_lang, True
            if existing.lang_code != sender_lang:
                existing.lang_code = sender_lang
                session.commit()

        return username, user_id, sender_lang, False

    def register_commands(self) -> None:
        """Register all bot command handlers."""

        @self.bot_client.on(events.NewMessage(pattern=r"^/start(?:\s|$)"))
        async def start_command(event):
            username, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            log.info("/start from @%s (id=%s)", username, user_id)
            await event.respond(t("welcome", lang, username=username))

        @self.bot_client.on(events.NewMessage(pattern=r"^/add_channel(?:\s|$)"))
        async def add_channel_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            client_event = event.client
            await event.respond(t("add_channel_prompt", lang))
            try:
                async with client_event.conversation(event.chat_id, timeout=60) as conv:
                    response = await conv.wait_event(events.NewMessage(from_users=user_id))
                    channel_identifier = (response.raw_text or "").strip()

                    if channel_identifier.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return
            except AsyncTimeoutError:
                await event.respond(t("timed_out", lang, command="/add_channel"))
                return

            # Normalize: strip common prefixes
            txt = channel_identifier
            prefixes = [
                "https://t.me/",
                "http://t.me/",
                "https://telegram.me/",
                "http://telegram.me/",
                "t.me/",
                "telegram.me/",
                "tg://resolve?domain=",
            ]
            for p in prefixes:
                if txt.startswith(p):
                    txt = txt[len(p):]
                    break
            if txt.startswith("@"):
                txt = txt[1:]
            channel_identifier = txt.strip()

            # Detect invite link (+HASH or joinchat/HASH)
            invite_hash = None
            if channel_identifier.startswith("+"):
                invite_hash = channel_identifier[1:]
            elif channel_identifier.startswith("joinchat/"):
                invite_hash = channel_identifier[len("joinchat/"):]

            if invite_hash:
                if not _INVITE_HASH_RE.match(invite_hash):
                    await event.respond(t("invalid_invite_link", lang))
                    return
                log.info("/add_channel invite_hash='%s' from user_id=%s", invite_hash, user_id)
                success, result, db_id = await self.client_commands.join_channel("", user_id, invite_hash=invite_hash, lang=lang)
            else:
                if not _CHANNEL_RE.match(channel_identifier):
                    await event.respond(t("invalid_channel_id", lang))
                    return
                log.info("/add_channel '%s' from user_id=%s", channel_identifier, user_id)
                success, result, db_id = await self.client_commands.join_channel(channel_identifier, user_id, lang=lang)

            await event.respond(result)

            # Backfill: scan existing messages
            if success and db_id:
                await event.respond(t("scanning_messages", lang))
                matches = await self.client_commands.backfill_channel(db_id, user_id)
                if matches > 0:
                    await event.respond(t("backfill_matches", lang, count=matches))
                else:
                    await event.respond(t("backfill_no_matches", lang))

        @self.bot_client.on(events.NewMessage(pattern=r"^/list_channels(?:\s|$)"))
        async def list_channels_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            channels = await self.client_commands.list_channels(user_id)
            if not channels:
                await event.respond(t("no_channels", lang))
                return

            await event.respond(t("your_channels", lang, channels="\n".join(channels)))

        @self.bot_client.on(events.NewMessage(pattern=r"^/remove_channel(?:\s|$)"))
        async def remove_channel_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            with self._session_factory() as session:
                user_channels = (
                    session.query(Channel.id, Channel.identifier, Channel.title)
                    .join(UserChannel, UserChannel.channel_id == Channel.id)
                    .filter(UserChannel.user_id == user_id)
                    .all()
                )
                if not user_channels:
                    await event.respond(t("no_channels", lang))
                    return

                lines = []
                channel_data = []
                for i, ch in enumerate(user_channels, 1):
                    display = f"{ch.title} ({ch.identifier})" if ch.title else ch.identifier
                    lines.append(f"{i}. {display}")
                    channel_data.append({"id": ch.id, "display": display})

            client_event = event.client
            await event.respond(t("remove_channel_prompt", lang, channels="\n".join(lines)))
            try:
                async with client_event.conversation(event.chat_id, timeout=60) as conv:
                    resp = await conv.wait_event(events.NewMessage(from_users=user_id))
                    choice = (resp.raw_text or "").strip()

                    if choice.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return

                    try:
                        idx = int(choice) - 1
                    except ValueError:
                        await conv.send_message(t("invalid_choice", lang, command="/remove_channel"))
                        return

                    if idx < 0 or idx >= len(channel_data):
                        await conv.send_message(t("number_out_of_range", lang, command="/remove_channel"))
                        return

            except AsyncTimeoutError:
                await event.respond(t("timed_out", lang, command="/remove_channel"))
                return

            chosen = channel_data[idx]
            log.info("/remove_channel '%s' from user_id=%s", chosen["display"], user_id)
            with self._session_factory() as session:
                link = session.query(UserChannel).filter_by(
                    user_id=user_id, channel_id=chosen["id"]
                ).first()
                if link:
                    session.delete(link)
                    session.commit()

            await event.respond(t("remove_channel_removed", lang, channel=chosen["display"]))

        @self.bot_client.on(events.NewMessage(pattern=r"^/watch(?:\s|$)"))
        async def watch_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            client_event = event.client
            await event.respond(t("watch_ask_product", lang))
            try:
                async with client_event.conversation(event.chat_id, timeout=60) as conv:
                    resp = await conv.wait_event(events.NewMessage(from_users=user_id))
                    product_name = (resp.raw_text or "").strip()

                    if product_name.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return

                    await conv.send_message(t("watch_ask_price", lang))
                    resp2 = await conv.wait_event(events.NewMessage(from_users=user_id))
                    price_text = (resp2.raw_text or "").strip()

                    if price_text.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return

                    target_price = None
                    if price_text.lower() not in _SKIP_KEYWORDS:
                        cleaned = price_text.replace("€", "").replace("EUR", "").replace("euro", "").strip()
                        cleaned = cleaned.replace(",", ".")
                        try:
                            target_price = float(cleaned)
                        except ValueError:
                            await conv.send_message(t("watch_invalid_price", lang))
                            return

                    await conv.send_message(t("watch_ask_category", lang))
                    resp3 = await conv.wait_event(events.NewMessage(from_users=user_id))
                    cat_text = (resp3.raw_text or "").strip()

                    if cat_text.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return

                    category = None
                    if cat_text.lower() not in _SKIP_KEYWORDS:
                        category = cat_text.lower()

            except AsyncTimeoutError:
                await event.respond(t("timed_out", lang, command="/watch"))
                return

            product_name_lower = product_name.lower()
            with self._session_factory() as session:
                existing = session.query(Product).filter_by(
                    user_id=user_id, name=product_name_lower
                ).first()
                if existing:
                    await event.respond(t("watch_already_monitoring", lang, product=product_name))
                    return

                # If there's price history for this product, suggest the minimum price
                if target_price is None:
                    from sqlalchemy import func
                    min_price_row = (
                        session.query(func.min(PriceHistory.price))
                        .join(Product, Product.id == PriceHistory.product_id)
                        .filter(Product.name == product_name_lower, PriceHistory.price.isnot(None))
                        .scalar()
                    )
                    if min_price_row is not None:
                        suggested_price = min_price_row

            # If we have a suggested price from history, ask the user
            if target_price is None and 'suggested_price' in dir():
                if suggested_price is not None:
                    client_event = event.client
                    await event.respond(
                        t("watch_suggest_price", lang, product=product_name, price=suggested_price)
                    )
                    try:
                        async with client_event.conversation(event.chat_id, timeout=60) as conv:
                            resp_suggest = await conv.wait_event(events.NewMessage(from_users=user_id))
                            answer = (resp_suggest.raw_text or "").strip().lower()
                            if answer in {"si", "sì", "yes", "ok"}:
                                target_price = suggested_price
                            elif answer not in _SKIP_KEYWORDS | {"no"}:
                                cleaned = answer.replace("€", "").replace("EUR", "").replace("euro", "").replace(",", ".").strip()
                                try:
                                    target_price = float(cleaned)
                                except ValueError:
                                    pass
                    except AsyncTimeoutError:
                        pass

            with self._session_factory() as session:
                session.add(Product(
                    user_id=user_id,
                    name=product_name_lower,
                    target_price=target_price,
                    category=category,
                ))
                session.commit()

            price_info = f" at ≤{target_price:.2f}" if target_price else " at any price"
            cat_info = f" [{category}]" if category else ""
            log.info("/watch '%s'%s%s from user_id=%s", product_name, price_info, cat_info, user_id)
            await event.respond(t("watch_active", lang, product=product_name, price_info=price_info, cat_info=cat_info))

        @self.bot_client.on(events.NewMessage(pattern=r"^/list_products(?:\s|$)"))
        async def list_products_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=user_id).all()

                if not products:
                    await event.respond(t("no_products", lang))
                    return

                lines = []
                for i, p in enumerate(products, 1):
                    price_str = f"≤{p.target_price:.2f}" if p.target_price else "any price"
                    lines.append(f"{i}. {p.name} ({price_str})")
                await event.respond(t("your_products", lang, products="\n".join(lines)))

        @self.bot_client.on(events.NewMessage(pattern=r"^/unwatch(?:\s|$)"))
        async def unwatch_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=user_id).all()

                if not products:
                    await event.respond(t("no_products_short", lang))
                    return

                lines = []
                product_ids = []
                for i, p in enumerate(products, 1):
                    price_str = f"≤{p.target_price:.2f}" if p.target_price else "any price"
                    lines.append(f"{i}. {p.name} ({price_str})")
                    product_ids.append({"id": p.id, "name": p.name})

            client_event = event.client
            await event.respond(t("unwatch_prompt", lang, products="\n".join(lines)))
            try:
                async with client_event.conversation(event.chat_id, timeout=60) as conv:
                    resp = await conv.wait_event(events.NewMessage(from_users=user_id))
                    choice = (resp.raw_text or "").strip()

                    if choice.lower() in _CANCEL_KEYWORDS:
                        await conv.send_message(t("operation_cancelled", lang))
                        return

                    try:
                        idx = int(choice) - 1
                    except ValueError:
                        await conv.send_message(t("invalid_choice", lang, command="/unwatch"))
                        return

                    if idx < 0 or idx >= len(product_ids):
                        await conv.send_message(t("number_out_of_range", lang, command="/unwatch"))
                        return

            except AsyncTimeoutError:
                await event.respond(t("timed_out", lang, command="/unwatch"))
                return

            chosen = product_ids[idx]
            log.info("/unwatch '%s' from user_id=%s", chosen["name"], user_id)
            with self._session_factory() as session:
                product = session.query(Product).filter_by(id=chosen["id"]).first()
                if product:
                    session.delete(product)
                    session.commit()

            await event.respond(t("unwatched", lang, product=chosen['name']))

        @self.bot_client.on(events.NewMessage(pattern=r"^/history(?:\s|$)"))
        async def history_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=user_id).all()
                if not products:
                    await event.respond(t("no_products_short", lang))
                    return

                product_data = [{"id": p.id, "name": p.name} for p in products]

            if len(product_data) == 1:
                chosen = product_data[0]
            else:
                lines = [f"{i}. {p['name']}" for i, p in enumerate(product_data, 1)]
                client_event = event.client
                await event.respond(t("history_prompt", lang, products="\n".join(lines)))
                try:
                    async with client_event.conversation(event.chat_id, timeout=60) as conv:
                        resp = await conv.wait_event(events.NewMessage(from_users=user_id))
                        choice = (resp.raw_text or "").strip()
                        if choice.lower() in _CANCEL_KEYWORDS:
                            await conv.send_message(t("operation_cancelled", lang))
                            return
                        try:
                            idx = int(choice) - 1
                        except ValueError:
                            await conv.send_message(t("invalid_choice", lang, command="/history"))
                            return
                        if idx < 0 or idx >= len(product_data):
                            await conv.send_message(t("number_out_of_range", lang, command="/history"))
                            return
                except AsyncTimeoutError:
                    await event.respond(t("timed_out", lang, command="/history"))
                    return
                chosen = product_data[idx]

            log.info("/history '%s' from user_id=%s", chosen["name"], user_id)
            with self._session_factory() as session:
                entries = (
                    session.query(PriceHistory)
                    .filter_by(product_id=chosen["id"])
                    .order_by(PriceHistory.found_at.desc())
                    .limit(10)
                    .all()
                )
                if not entries:
                    await event.respond(t("history_empty", lang, product=chosen['name']))
                    return

                lines = [t("history_header", lang, product=chosen['name'], count=len(entries))]
                for e in entries:
                    date_str = e.found_at[:16].replace("T", " ")
                    price_str = f"{e.price:.2f}" if e.price else "N/A"
                    link_str = f" link" if e.message_link else ""
                    lines.append(f"  {date_str} | {price_str} | {e.channel}{link_str}")
                await event.respond("\n".join(lines))

        @self.bot_client.on(events.NewMessage(pattern=r"^/pause(?:\s|$)"))
        async def pause_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            log.info("/pause from user_id=%s", user_id)
            with self._session_factory() as session:
                user = session.query(User).filter_by(user_id=user_id).first()
                if user:
                    user.paused = True
                    session.commit()
            await event.respond(t("paused", lang))

        @self.bot_client.on(events.NewMessage(pattern=r"^/resume(?:\s|$)"))
        async def resume_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            log.info("/resume from user_id=%s", user_id)
            with self._session_factory() as session:
                user = session.query(User).filter_by(user_id=user_id).first()
                if user:
                    user.paused = False
                    session.commit()
            await event.respond(t("resumed", lang))

        @self.bot_client.on(events.NewMessage(pattern=r"^/stats(?:\s|$)"))
        async def stats_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            log.info("/stats from user_id=%s", user_id)
            with self._session_factory() as session:
                from sqlalchemy import func
                from models import UserChannel

                n_products = session.query(Product).filter_by(user_id=user_id).count()
                n_channels = session.query(UserChannel).filter_by(user_id=user_id).count()
                n_matches = session.query(PriceHistory).filter_by(user_id=user_id).count()

                lines = [
                    t("stats_header", lang),
                    t("stats_products", lang, count=n_products),
                    t("stats_channels", lang, count=n_channels),
                    t("stats_matches", lang, count=n_matches),
                ]

                if n_matches > 0:
                    # Most matched product
                    top = (
                        session.query(Product.name, func.count(PriceHistory.id).label("cnt"))
                        .join(PriceHistory, PriceHistory.product_id == Product.id)
                        .filter(PriceHistory.user_id == user_id)
                        .group_by(Product.name)
                        .order_by(func.count(PriceHistory.id).desc())
                        .first()
                    )
                    if top:
                        lines.append(t("stats_top_product", lang, name=top[0], count=top[1]))

                    # Most active channel
                    top_ch = (
                        session.query(PriceHistory.channel, func.count(PriceHistory.id).label("cnt"))
                        .filter(PriceHistory.user_id == user_id)
                        .group_by(PriceHistory.channel)
                        .order_by(func.count(PriceHistory.id).desc())
                        .first()
                    )
                    if top_ch:
                        lines.append(t("stats_top_channel", lang, name=top_ch[0], count=top_ch[1]))

                    # Last match
                    last = (
                        session.query(PriceHistory)
                        .filter_by(user_id=user_id)
                        .order_by(PriceHistory.found_at.desc())
                        .first()
                    )
                    if last:
                        date_str = last.found_at[:16].replace("T", " ")
                        lines.append(t("stats_last_match", lang, date=date_str))

                await event.respond("\n".join(lines))

        @self.bot_client.on(events.NewMessage(pattern=r"^/list_categories(?:\s|$)"))
        async def list_categories_command(event):
            _, user_id, lang, _ = await self.register_user_if_not_exists(event)
            if user_id is None:
                await event.respond(t("start_first", lang))
                return
            if not self._is_authorized(user_id):
                await event.respond(t("not_authorized", lang))
                return

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=user_id).all()
                if not products:
                    await event.respond(t("no_products_short", lang))
                    return

                by_category = {}
                for p in products:
                    cat = p.category or t("uncategorized", lang)
                    by_category.setdefault(cat, []).append(p.name)

                lines = [t("categories_header", lang)]
                for cat, names in sorted(by_category.items()):
                    lines.append(f"\n{cat}:")
                    for name in names:
                        lines.append(f"  - {name}")
                await event.respond("\n".join(lines))
