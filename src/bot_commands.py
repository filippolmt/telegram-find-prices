"""
Bot command handlers for Telegram bot interactions.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import sessionmaker
from telethon import TelegramClient, events

from amazon import first_product_link, slug_keywords, urls_in_text
from channel_folder import ChannelFolder
from client_commands import ClientCommands
from command_context import CommandContext
from config import Config, is_authorized
from match_recorder import has_keywords
from models import Channel, PriceHistory, Product, User, UserChannel
from price_parser import parse_target_price
from prompts import NO_KEYWORDS, SKIP_KEYWORDS, YES_KEYWORDS, conversation
from translations import DEFAULT_LANGUAGE, resolve_lang, t

log = logging.getLogger(__name__)

_CHANNEL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$")
_INVITE_HASH_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_CHANNEL_PREFIXES = (
    "https://t.me/",
    "http://t.me/",
    "https://telegram.me/",
    "http://telegram.me/",
    "t.me/",
    "telegram.me/",
    "tg://resolve?domain=",
)


class ChannelRef(StrEnum):
    USERNAME = "username"
    INVITE = "invite"
    INVALID_USERNAME = "invalid_username"
    INVALID_INVITE = "invalid_invite"


def parse_channel_ref(text: str) -> tuple[ChannelRef, str | None]:
    """Parse a user-supplied channel reference into (kind, username or invite hash); value None if invalid."""
    ref = text.strip()
    for prefix in _CHANNEL_PREFIXES:
        if ref.startswith(prefix):
            ref = ref[len(prefix):]
            break
    ref = ref.removeprefix("@").strip()

    invite_hash = None
    if ref.startswith("+"):
        invite_hash = ref[1:]
    elif ref.startswith("joinchat/"):
        invite_hash = ref[len("joinchat/"):]
    if invite_hash:
        if _INVITE_HASH_RE.fullmatch(invite_hash):
            return ChannelRef.INVITE, invite_hash
        return ChannelRef.INVALID_INVITE, None
    if _CHANNEL_RE.fullmatch(ref):
        return ChannelRef.USERNAME, ref
    return ChannelRef.INVALID_USERNAME, None


def _price_label(target_price: float | None, lang: str) -> str:
    return f"≤{target_price:.2f}" if target_price else t("any_price", lang)


def _channel_label(channel) -> str:
    return f"{channel.title} ({channel.identifier})" if channel.title else channel.identifier


def _command_argument(event) -> str:
    """The text after the command ('/watch <link>'): it answers the command's first question. '' if none."""
    parts = (event.raw_text or "").split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


CommandFlow = Callable[[events.NewMessage.Event, CommandContext], Awaitable[None]]


class BotCommands:
    """Telegram bot command handlers."""

    def __init__(
        self,
        bot_client: TelegramClient,
        client_commands: ClientCommands,
        db_session_factory: sessionmaker,
        channel_folder: ChannelFolder | None = None,
    ):
        self.bot_client = bot_client
        self.channel_folder = channel_folder
        self.client_commands = client_commands
        self._session_factory = db_session_factory
        self._allowed_users = Config.ALLOWED_USERS
        self._allow_all = Config.ALLOW_ALL_USERS

    def _is_authorized(self, user_id: int | None) -> bool:
        return is_authorized(user_id, self._allowed_users, self._allow_all)

    async def register_user_if_not_exists(self, event: events.NewMessage.Event) -> Optional[CommandContext]:
        """Identify the sender and register them if authorized and not yet registered.

        Returns None when the sender has no user id or username.
        """
        tg_sender = await event.get_sender()
        user_id: Optional[int] = getattr(event, "sender_id", None)
        username: Optional[str] = getattr(tg_sender, "username", None)
        if user_id is None or username is None:
            return None
        sender = CommandContext(user_id, username, resolve_lang(getattr(tg_sender, "lang_code", None)))

        if not self._is_authorized(user_id):
            # Never persist strangers: this check, not the gate order, keeps them out of the DB
            return sender

        with self._session_factory() as session:
            existing = session.get(User, user_id)
            if existing is None:
                session.add(User(id=user_id, user_id=user_id, username=username, lang_code=sender.lang))
                session.commit()
            elif existing.lang_code != sender.lang:
                existing.lang_code = sender.lang
                session.commit()

        return sender

    def _gate(self, flow: CommandFlow, missing_identity_reply: str = "start_first") -> Callable[[events.NewMessage.Event], Awaitable[None]]:
        """Wrap a command flow: resolve, authorize and register the sender, then run the flow with its context."""

        async def handler(event) -> None:
            sender = await self.register_user_if_not_exists(event)
            if sender is None:
                await event.respond(t(missing_identity_reply, DEFAULT_LANGUAGE))
                return
            if not self._is_authorized(sender.user_id):
                await event.respond(t("not_authorized", sender.lang))
                return
            await flow(event, sender)

        return handler

    def _command(self, name: str, missing_identity_reply: str = "start_first") -> Callable[[CommandFlow], CommandFlow]:
        """Register a flow for /name behind the gate."""

        def register(flow: CommandFlow) -> CommandFlow:
            self.bot_client.on(events.NewMessage(pattern=rf"^/{name}(?:\s|$)"))(self._gate(flow, missing_identity_reply))
            return flow

        return register

    def register_commands(self) -> None:
        """Register all bot command handlers."""

        @self._command("start", missing_identity_reply="not_authorized")
        async def start_command(event, ctx):

            log.info("/start from @%s (id=%s)", ctx.username, ctx.user_id)
            await event.respond(t("welcome", ctx.lang, username=ctx.username))
            # The owner's /start is what the Channel folder waits for: read it now, not at the next poll
            if self.channel_folder and ctx.user_id == await self.channel_folder.owner_id():
                count = await self.channel_folder.sync()
                if count is not None:
                    await event.respond(t("folder_channels_monitored", ctx.lang,
                                          folder=self.channel_folder.folder_name, count=count))

        @self._command("add_channel")
        async def add_channel_command(event, ctx):

            async with conversation(event, ctx, "/add_channel") as ask:
                channel_identifier = _command_argument(event) or await ask.text("add_channel_prompt")
            if channel_identifier is None:
                return

            kind, value = parse_channel_ref(channel_identifier)
            if kind is ChannelRef.INVALID_INVITE:
                await event.respond(t("invalid_invite_link", ctx.lang))
                return
            if kind is ChannelRef.INVALID_USERNAME:
                await event.respond(t("invalid_channel_id", ctx.lang))
                return
            if kind is ChannelRef.INVITE:
                # The invite hash grants channel access: never log it in full
                log.info("/add_channel invite_hash='%s…' from user_id=%s", value[:4], ctx.user_id)
                success, result, db_id = await self.client_commands.join_channel("", ctx.user_id, invite_hash=value, lang=ctx.lang)
            else:
                log.info("/add_channel '%s' from user_id=%s", value, ctx.user_id)
                success, result, db_id = await self.client_commands.join_channel(value, ctx.user_id, lang=ctx.lang)

            await event.respond(result)

            # Backfill: scan existing messages
            if success and db_id:
                await event.respond(t("scanning_messages", ctx.lang))
                matches = await self.client_commands.backfill_channel(db_id, ctx.user_id)
                if matches > 0:
                    await event.respond(t("backfill_matches", ctx.lang, count=matches))
                else:
                    await event.respond(t("backfill_no_matches", ctx.lang))

        @self._command("list_channels")
        async def list_channels_command(event, ctx):

            channels = await self.client_commands.list_channels(ctx.user_id)
            if not channels:
                await event.respond(t("no_channels", ctx.lang))
                return

            await event.respond(t("your_channels", ctx.lang, channels="\n".join(channels)))

        @self._command("remove_channel")
        async def remove_channel_command(event, ctx):

            with self._session_factory() as session:
                user_channels = (
                    session.query(Channel.id, Channel.identifier, Channel.title)
                    .join(UserChannel, UserChannel.channel_id == Channel.id)
                    .filter(UserChannel.user_id == ctx.user_id)
                    .all()
                )
                if not user_channels:
                    await event.respond(t("no_channels", ctx.lang))
                    return

            async with conversation(event, ctx, "/remove_channel") as ask:
                chosen = await ask.pick("remove_channel_prompt", [(_channel_label(ch), ch) for ch in user_channels])
            if chosen is None:
                return
            display = _channel_label(chosen)
            log.info("/remove_channel '%s' from user_id=%s", display, ctx.user_id)
            with self._session_factory() as session:
                link = session.query(UserChannel).filter_by(
                    user_id=ctx.user_id, channel_id=chosen.id
                ).first()
                if link:
                    session.delete(link)
                    session.commit()

            await event.respond(t("remove_channel_removed", ctx.lang, channel=display))

        @self._command("watch")
        async def watch_command(event, ctx):

            async with conversation(event, ctx, "/watch") as ask:
                product_name = _command_argument(event) or await ask.text("watch_ask_product")
                if product_name is None:
                    return

                asin = None
                if link := await first_product_link(product_name):
                    asin, url = link
                    suggested = slug_keywords(url)
                    if suggested:
                        keywords = await ask.text("watch_asin_keywords", asin=asin, keywords=suggested)
                    else:
                        keywords = await ask.text("watch_asin_no_keywords", asin=asin)
                    if keywords is None:
                        return
                    if suggested and keywords.lower() in YES_KEYWORDS:
                        product_name = suggested
                    elif has_keywords(keywords) and keywords.lower() not in SKIP_KEYWORDS:
                        product_name = keywords
                    else:
                        # Match by link only: the ASIN as name also matches posts quoting it
                        product_name = asin
                elif urls_in_text(product_name):
                    # Never store (or log) an unreadable link, with its tracking params, as keywords
                    await event.respond(t("watch_link_not_product", ctx.lang))
                    return
                elif not has_keywords(product_name):
                    # A sticker or punctuation as name would match every post
                    await event.respond(t("watch_name_no_keywords", ctx.lang))
                    return

                price_text = await ask.text("watch_ask_price")
                if price_text is None:
                    return
                target_price = None
                if price_text.lower() not in SKIP_KEYWORDS:
                    target_price = parse_target_price(price_text)
                    if target_price is None:
                        await event.respond(t("watch_invalid_price", ctx.lang))
                        return

                cat_text = await ask.text("watch_ask_category")
                if cat_text is None:
                    return
                category = None if cat_text.lower() in SKIP_KEYWORDS else cat_text.lower()

                product_name_lower = product_name.lower()
                suggested_price = None
                with self._session_factory() as session:
                    existing = session.query(Product).filter(
                        Product.user_id == ctx.user_id,
                        or_(Product.name == product_name_lower, and_(Product.asin.isnot(None), Product.asin == asin)),
                    ).first()
                    if existing:
                        await event.respond(t("watch_already_monitoring", ctx.lang, product=product_name))
                        return

                    # If there's price history for this product, suggest the minimum price
                    if target_price is None:
                        suggested_price = (
                            session.query(func.min(PriceHistory.price))
                            .join(Product, Product.id == PriceHistory.product_id)
                            .filter(Product.name == product_name_lower, PriceHistory.price.isnot(None))
                            .scalar()
                        )

                # Price history for this product: offer its minimum as target
                if suggested_price is not None:
                    answer = await ask.text("watch_suggest_price", product=product_name, price=suggested_price)
                    if answer is None:
                        return
                    answer = answer.lower()
                    if answer in YES_KEYWORDS:
                        target_price = suggested_price
                    elif answer not in SKIP_KEYWORDS | NO_KEYWORDS:
                        target_price = parse_target_price(answer)
                        if target_price is None:
                            await event.respond(t("watch_invalid_price", ctx.lang))
                            return

            with self._session_factory() as session:
                session.add(Product(
                    user_id=ctx.user_id,
                    name=product_name_lower,
                    target_price=target_price,
                    category=category,
                    asin=asin,
                ))
                session.commit()

            log.info("/watch '%s' asin=%s target=%s category=%s from user_id=%s", product_name, asin, target_price, category, ctx.user_id)
            price_info = t("watch_price_info", ctx.lang, price=_price_label(target_price, ctx.lang))
            cat_info = f" [{category}]" if category else ""
            await event.respond(t("watch_active", ctx.lang, product=product_name, price_info=price_info, cat_info=cat_info))

        @self._command("list_products")
        async def list_products_command(event, ctx):

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=ctx.user_id).all()

                if not products:
                    await event.respond(t("no_products", ctx.lang))
                    return

                lines = [f"{i}. {p.name} ({_price_label(p.target_price, ctx.lang)})" for i, p in enumerate(products, 1)]
                await event.respond(t("your_products", ctx.lang, products="\n".join(lines)))

        @self._command("unwatch")
        async def unwatch_command(event, ctx):

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=ctx.user_id).all()

                if not products:
                    await event.respond(t("no_products_short", ctx.lang))
                    return

                choices = [(f"{p.name} ({_price_label(p.target_price, ctx.lang)})", p) for p in products]

            async with conversation(event, ctx, "/unwatch") as ask:
                chosen = await ask.pick("unwatch_prompt", choices)
            if chosen is None:
                return
            log.info("/unwatch '%s' from user_id=%s", chosen.name, ctx.user_id)
            with self._session_factory() as session:
                product = session.get(Product, chosen.id)
                if product:
                    session.delete(product)
                    session.commit()

            await event.respond(t("unwatched", ctx.lang, product=chosen.name))

        @self._command("history")
        async def history_command(event, ctx):

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=ctx.user_id).all()
                if not products:
                    await event.respond(t("no_products_short", ctx.lang))
                    return

            if len(products) == 1:
                chosen = products[0]
            else:
                async with conversation(event, ctx, "/history") as ask:
                    chosen = await ask.pick("history_prompt", [(p.name, p) for p in products])
                if chosen is None:
                    return

            log.info("/history '%s' from user_id=%s", chosen.name, ctx.user_id)
            with self._session_factory() as session:
                entries = (
                    session.query(PriceHistory)
                    .filter_by(product_id=chosen.id)
                    .order_by(PriceHistory.found_at.desc())
                    .limit(10)
                    .all()
                )
                if not entries:
                    await event.respond(t("history_empty", ctx.lang, product=chosen.name))
                    return

                lines = [t("history_header", ctx.lang, product=chosen.name, count=len(entries))]
                for e in entries:
                    date_str = e.found_at[:16].replace("T", " ")
                    price_str = f"{e.price:.2f}" if e.price else t("no_price", ctx.lang)
                    link_str = " link" if e.message_link else ""
                    lines.append(f"  {date_str} | {price_str} | {e.channel}{link_str}")
                await event.respond("\n".join(lines))

        @self._command("pause")
        async def pause_command(event, ctx):

            log.info("/pause from user_id=%s", ctx.user_id)
            with self._session_factory() as session:
                user = session.query(User).filter_by(user_id=ctx.user_id).first()
                if user:
                    user.paused = True
                    session.commit()
            await event.respond(t("paused", ctx.lang))

        @self._command("resume")
        async def resume_command(event, ctx):

            log.info("/resume from user_id=%s", ctx.user_id)
            with self._session_factory() as session:
                user = session.query(User).filter_by(user_id=ctx.user_id).first()
                if user:
                    user.paused = False
                    session.commit()
            await event.respond(t("resumed", ctx.lang))

        @self._command("stats")
        async def stats_command(event, ctx):

            log.info("/stats from user_id=%s", ctx.user_id)
            with self._session_factory() as session:
                n_products = session.query(Product).filter_by(user_id=ctx.user_id).count()
                n_channels = session.query(UserChannel).filter_by(user_id=ctx.user_id).count()
                n_matches = session.query(PriceHistory).filter_by(user_id=ctx.user_id).count()

                lines = [
                    t("stats_header", ctx.lang),
                    t("stats_products", ctx.lang, count=n_products),
                    t("stats_channels", ctx.lang, count=n_channels),
                    t("stats_matches", ctx.lang, count=n_matches),
                ]

                if n_matches > 0:
                    # Most matched product
                    top = (
                        session.query(Product.name, func.count(PriceHistory.id).label("cnt"))
                        .join(PriceHistory, PriceHistory.product_id == Product.id)
                        .filter(PriceHistory.user_id == ctx.user_id)
                        .group_by(Product.name)
                        .order_by(func.count(PriceHistory.id).desc())
                        .first()
                    )
                    if top:
                        lines.append(t("stats_top_product", ctx.lang, name=top[0], count=top[1]))

                    # Most active channel
                    top_ch = (
                        session.query(PriceHistory.channel, func.count(PriceHistory.id).label("cnt"))
                        .filter(PriceHistory.user_id == ctx.user_id)
                        .group_by(PriceHistory.channel)
                        .order_by(func.count(PriceHistory.id).desc())
                        .first()
                    )
                    if top_ch:
                        lines.append(t("stats_top_channel", ctx.lang, name=top_ch[0], count=top_ch[1]))

                    # Last match
                    last = (
                        session.query(PriceHistory)
                        .filter_by(user_id=ctx.user_id)
                        .order_by(PriceHistory.found_at.desc())
                        .first()
                    )
                    if last:
                        date_str = last.found_at[:16].replace("T", " ")
                        lines.append(t("stats_last_match", ctx.lang, date=date_str))

                await event.respond("\n".join(lines))

        @self._command("list_categories")
        async def list_categories_command(event, ctx):

            with self._session_factory() as session:
                products = session.query(Product).filter_by(user_id=ctx.user_id).all()
                if not products:
                    await event.respond(t("no_products_short", ctx.lang))
                    return

                by_category = {}
                for p in products:
                    cat = p.category or t("uncategorized", ctx.lang)
                    by_category.setdefault(cat, []).append(p.name)

                lines = [t("categories_header", ctx.lang)]
                for cat, names in sorted(by_category.items()):
                    lines.append(f"\n{cat}:")
                    for name in names:
                        lines.append(f"  - {name}")
                await event.respond("\n".join(lines))
