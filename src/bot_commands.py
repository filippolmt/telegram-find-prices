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
from telethon.errors import RPCError
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeUsers

from amazon import first_product_link, slug_keywords, urls_in_text
from channel_changes import ChannelChanges, Decision, request_label
from channel_folder import ChannelFolder, MonitoredChannels
from channel_requests import ChannelRequests
from client_commands import ClientCommands
from command_context import CommandContext
from config import Config, is_authorized
from match_recorder import has_keywords
from models import (
    Channel,
    ChannelInfo,
    ChannelRequestAction,
    PriceHistory,
    Product,
    User,
)
from price_parser import parse_target_price
from prompts import NO_KEYWORDS, SKIP_KEYWORDS, YES_KEYWORDS, conversation
from translations import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, t

log = logging.getLogger(__name__)

# Data of the Approve/Reject buttons of a Channel request: "<decision>:<request id>"
_REQUEST_BUTTON = re.compile(rf"^({'|'.join(Decision)}):(\d+)$".encode())


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
        self.channel_requests = ChannelRequests(db_session_factory)
        self.channel_changes = ChannelChanges(bot_client, client_commands, MonitoredChannels(client_commands, channel_folder),
                                              self.channel_requests, db_session_factory)
        if channel_folder:
            # A channel the owner moves in or out of the folder by hand answers the requests for it
            channel_folder.on_changed = self.channel_changes.answer_requests
        self._allowed_users = Config.ALLOWED_USERS
        self._allow_all = Config.ALLOW_ALL_USERS

    def _is_authorized(self, user_id: int | None) -> bool:
        return is_authorized(user_id, self._allowed_users, self._allow_all)

    async def _owner_pressing(self, event) -> CommandContext | None:
        """The owner who pressed a request button, or None after refusing (and logging) anyone else.

        Checked when it runs: the owner is whoever the account is now.
        """
        sender = await self._identify(event)
        if sender is None or sender.user_id != await self.client_commands.owner_id():
            log.warning("Channel request button pressed by user_id=%s, not the owner: refused", event.sender_id)
            await event.answer(t("owner_only_button", sender.lang if sender else DEFAULT_LANGUAGE))
            return None
        return sender

    async def _reject(self, event, owner: CommandContext, request_id: int) -> None:
        request = self.channel_requests.get(request_id)
        if request is None:
            await event.respond(t("request_already_decided", owner.lang))
            return
        label = request_label(request, owner.lang)
        # Cancelled or timed out: the request stays pending
        async with conversation(event, owner, "/requests") as ask:
            while not (reason := await ask.text("reject_reason_prompt", channel=label)):
                if reason is None:
                    return
                await event.respond(t("reject_reason_required", owner.lang))
        if not await self._still_owner(event, owner, "owner_only_button"):
            return
        if not await self.channel_changes.reject(request, label, reason):
            # Approved while the owner was typing the reason
            await event.respond(t("request_already_decided", owner.lang))
            return
        await event.respond(t("request_rejected", owner.lang, channel=label))

    async def _still_owner(self, event, ctx: CommandContext, refusal_key: str) -> bool:
        """Whether the owner who started a conversation is still the owner once it ends; refused and logged if not."""
        if ctx.user_id == await self.client_commands.owner_id():
            return True
        log.warning("user_id=%s is no longer the owner when the conversation ends: refused", ctx.user_id)
        await event.respond(t(refusal_key, ctx.lang))
        return False

    async def _owner_or_requester(self, event, ctx: CommandContext) -> bool | None:
        """Whether the sender changes channels as the owner (True) or by request (False); None after telling them
        they can do neither: without a Channel folder only the owner changes channels."""
        is_owner = ctx.user_id == await self.client_commands.owner_id()
        if not is_owner and not self.channel_folder:
            await event.respond(t("channels_owner_only", ctx.lang))
            return None
        return is_owner

    @staticmethod
    async def _identify(event: events.NewMessage.Event) -> Optional[CommandContext]:
        """The sender as a user, or None when it is not one: no id, or a channel's negative id (anonymous
        admins, linked channels). The username is optional: many accounts have none."""
        user_id: Optional[int] = getattr(event, "sender_id", None)
        if user_id is None or user_id <= 0:
            return None
        return CommandContext.from_sender(user_id, await event.get_sender())

    def _register(self, sender: CommandContext) -> None:
        """Store an authorized sender, or bring their username and language up to date."""
        with self._session_factory() as session:
            user = session.get(User, sender.user_id)
            if user is None:
                session.add(User(id=sender.user_id, user_id=sender.user_id, username=sender.username, lang_code=sender.lang))
            else:
                user.username, user.lang_code = sender.username, sender.lang
            session.commit()

    def _gate(self, flow: CommandFlow) -> Callable[[events.NewMessage.Event], Awaitable[None]]:
        """Wrap a command flow: resolve, authorize and register the sender, then run the flow with its context."""

        async def handler(event) -> None:
            sender = await self._identify(event)
            if sender is None:
                await event.respond(t("users_only", DEFAULT_LANGUAGE))
                return
            if not self._is_authorized(sender.user_id):
                # Strangers are never written to the DB: the log is how the owner learns an ID to allow.
                # The message text is left out: it may hold a link or an invite hash.
                log.warning("Rejected sender user_id=%s (%s)", sender.user_id,
                            f"@{sender.username}" if sender.username else "no username")
                await event.respond(t("not_authorized", sender.lang))
                return
            self._register(sender)
            await flow(event, sender)

        return handler

    def _command(self, name: str) -> Callable[[CommandFlow], CommandFlow]:
        """Register a flow for /name behind the gate."""

        def register(flow: CommandFlow) -> CommandFlow:
            self._command_names.append(name)
            pattern = rf"^/{name}{self._addressed_to_me}(?:\s|$)"
            self.bot_client.on(events.NewMessage(pattern=pattern))(self._gate(flow))
            return flow

        return register

    async def publish_commands(self) -> None:
        """Set the command menu users see in private chats to the registered commands, in every language.

        Replaces the list pasted in BotFather; a failure is logged, the bot runs without an up-to-date menu.
        """
        for lang in SUPPORTED_LANGUAGES:
            commands = [BotCommand(name, t(f"command_{name}", lang)) for name in self._command_names]
            try:
                # lang_code "": the menu for every language without its own
                await self.bot_client(SetBotCommandsRequest(
                    BotCommandScopeUsers(), "" if lang == DEFAULT_LANGUAGE else lang, commands))
            except RPCError as e:
                log.error("Command list not published for language '%s': %s", lang, e)

    def register_commands(self, bot_username: str = "") -> None:
        """Register all bot command handlers; also as /name@bot_username, the form group chats send."""
        self._command_names: list[str] = []
        # Telegram usernames are case-insensitive; a command for another bot matches nothing
        self._addressed_to_me = rf"(?i:@{re.escape(bot_username)})?" if bot_username else ""

        @self._command("start")
        async def start_command(event, ctx):

            log.info("/start from id=%s username=%s first_name=%s", ctx.user_id, ctx.username, ctx.first_name)
            await event.respond(t("welcome", ctx.lang, name=ctx.display_name))
            # The owner's /start reads the Channel folder now, not at the next poll
            if self.channel_folder and ctx.user_id == await self.client_commands.owner_id():
                count = await self.channel_folder.sync()
                if count is not None:
                    await event.respond(t("folder_channels_monitored", ctx.lang,
                                          folder=self.channel_folder.folder_name, count=count))

        @self._command("add_channel")
        async def add_channel_command(event, ctx):
            is_owner = await self._owner_or_requester(event, ctx)
            if is_owner is None:
                return

            async with conversation(event, ctx, "/add_channel") as ask:
                channel_identifier = await ask.text("add_channel_prompt", given=_command_argument(event))
            if channel_identifier is None:
                return

            kind, value = parse_channel_ref(channel_identifier)
            if kind is ChannelRef.INVALID_INVITE:
                await event.respond(t("invalid_invite_link", ctx.lang))
                return
            if kind is ChannelRef.INVALID_USERNAME:
                await event.respond(t("invalid_channel_id", ctx.lang))
                return
            identifier, invite_hash = (None, value) if kind is ChannelRef.INVITE else (value, None)
            # The invite hash grants channel access: never log it in full
            log.info("/add_channel '%s' from user_id=%s", identifier or f"invite {value[:4]}…", ctx.user_id)
            if is_owner:
                if await self._still_owner(event, ctx, "channels_owner_only"):
                    await self.channel_changes.add(event, ctx, identifier or "", invite_hash)
                return
            channel = ChannelInfo(identifier, None)
            if invite_hash:
                channel = await self.client_commands.check_invite(invite_hash)
                if channel is None:
                    await event.respond(t("invalid_invite_link", ctx.lang))
                    return
            if channel.identifier and (monitored := self.client_commands.find_channel(channel.identifier)):
                await event.respond(t("channel_already_monitored", ctx.lang, channel=monitored.label))
                return
            await self.channel_changes.file(event, ctx, ChannelRequestAction.ADD, channel, invite_hash)

        @self.bot_client.on(events.CallbackQuery(pattern=_REQUEST_BUTTON))
        async def request_button(event):
            sender = await self._owner_pressing(event)
            if sender is None:
                return
            await event.answer()
            decision, request_id = _REQUEST_BUTTON.match(event.data).groups()
            if Decision(decision.decode()) == Decision.APPROVE:
                await self.channel_changes.approve(event, sender, int(request_id))
            else:
                await self._reject(event, sender, int(request_id))

        @self._command("list_channels")
        async def list_channels_command(event, ctx):

            channels = self.client_commands.list_channels()
            text = t("monitored_channels", ctx.lang, channels="\n".join(channels)) if channels else t("no_channels", ctx.lang)
            if requests := self.channel_requests.pending(ctx.user_id):
                lines = [t(f"pending_line_{r.action}", ctx.lang, channel=request_label(r, ctx.lang)) for r in requests]
                text += t("your_pending_requests", ctx.lang, requests="\n".join(lines))
            await event.respond(text)

        @self._command("requests")
        async def requests_command(event, ctx):
            if ctx.user_id != await self.client_commands.owner_id():
                await event.respond(t("channels_owner_only", ctx.lang))
                return
            requests = self.channel_requests.pending()
            if not requests:
                await event.respond(t("no_requests", ctx.lang))
            for request in requests:
                await self.channel_changes.send_request(ctx.user_id, ctx.lang, request)

        @self._command("remove_channel")
        async def remove_channel_command(event, ctx):
            is_owner = await self._owner_or_requester(event, ctx)
            if is_owner is None:
                return
            channels = [(c.label, c) for c in self.client_commands.monitored_channels()]
            if not channels:
                await event.respond(t("no_channels", ctx.lang))
                return

            async with conversation(event, ctx, "/remove_channel") as ask:
                chosen = await ask.pick("remove_channel_prompt", channels)
            if chosen is None:
                return
            log.info("/remove_channel '%s' from user_id=%s", chosen.identifier, ctx.user_id)
            if is_owner:
                if await self._still_owner(event, ctx, "channels_owner_only"):
                    await self.channel_changes.remove(event, ctx, chosen.identifier)
            else:
                await self.channel_changes.file(event, ctx, ChannelRequestAction.REMOVE, chosen)

        @self._command("watch")
        async def watch_command(event, ctx):

            async with conversation(event, ctx, "/watch") as ask:
                product_name = await ask.text("watch_ask_product", given=_command_argument(event))
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
                n_channels = session.query(Channel).count()
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
