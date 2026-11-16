"""
Changes to the monitored channels, made by the owner directly or through the Channel requests that wait for them.

BotCommands holds the conversations; this module acts once they have an answer.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from sqlalchemy.orm import sessionmaker
from telethon import Button, TelegramClient

from channel_folder import MonitoredChannels
from channel_requests import ChannelRequests, Filed
from client_commands import ClientCommands
from command_context import CommandContext
from config import Config, is_authorized
from models import (
    ChannelInfo,
    ChannelRequest,
    ChannelRequestAction,
    User,
    channel_label,
)
from translations import resolve_lang, t

log = logging.getLogger(__name__)


class Decision(StrEnum):
    """The owner's choice on a Channel request; its button's data is "<decision>:<request id>"."""
    APPROVE = "approve"
    REJECT = "reject"


def request_label(request: ChannelRequest, lang: str) -> str:
    """How a request's channel is shown: an invite to a channel the account is not in shows only its hash's start."""
    return channel_label(request.identifier or t("invite_label", lang, hash=request.invite_hash[:4]), request.title)


class ChannelChanges:
    """Add and remove monitored channels, and file, decide and answer Channel requests.

    Methods taking (event, ctx) reply in that conversation, to ctx in its language.
    """

    def __init__(self, bot_client: TelegramClient, client_commands: ClientCommands, monitored: MonitoredChannels,
                 requests: ChannelRequests, db_session_factory: sessionmaker):
        self.bot_client = bot_client
        self.client_commands = client_commands
        self.monitored = monitored
        self.requests = requests
        self._session_factory = db_session_factory
        # One decision at a time: a second press of the same button finds the request decided
        self._decisions = asyncio.Lock()

    async def add(self, event, ctx: CommandContext, identifier: str, invite_hash: str | None) -> str | None:
        """The owner's account joins the channel, which becomes monitored: Backfill runs if it was not.

        Return the channel's label once monitored, None after telling the owner why it is not.
        """
        joined = await self.client_commands.join_channel(identifier, invite_hash)
        if joined is None:
            await event.respond(t("join_channel_failed", ctx.lang))
            return None
        identifier, title = joined
        label = joined.label
        # The account is in the channel now: a failure says so, the owner decides whether to leave it
        new = await self._change(event, ctx, "folder_add_failed", label, self.monitored.add(identifier, title))
        if new is None:
            return None
        await event.respond(t("channel_added", ctx.lang, channel=label))
        await self.answer_requests({identifier: label}, {})
        if new:
            await event.respond(t("scanning_messages", ctx.lang))
            matches = await self.client_commands.backfill_channel(identifier)
            await event.respond(t("backfill_matches", ctx.lang, count=matches) if matches else t("backfill_no_matches", ctx.lang))
        return label

    async def remove(self, event, ctx: CommandContext, identifier: str) -> str | None:
        """The channel stops being monitored and the owner's account leaves it.

        Return the channel's label once no longer monitored, None after telling the owner why it still is.
        """
        channel = self.client_commands.find_channel(identifier)
        label = channel.label if channel else identifier
        if await self._change(event, ctx, "folder_remove_failed", label, self.monitored.remove(identifier)) is None:
            return None
        await self.answer_requests({}, {identifier: label})
        left = await self.client_commands.leave_channel(identifier)
        await event.respond(t("channel_removed" if left else "channel_removed_not_left", ctx.lang, channel=label))
        return label

    async def _change(self, event, ctx: CommandContext, failed_key: str, label: str,
                      change: Awaitable[bool]) -> bool | None:
        """Await a change of the monitored channels; with a Channel folder, None after telling the owner it failed."""
        try:
            return await change
        except Exception as e:
            folder = self.monitored.folder_name
            if folder is None:
                raise
            # Missing or full folder, an id Telethon cannot resolve: the owner hears of each
            log.error("Channel folder '%s': changing '%s' failed: %r", folder, label, e)
            await event.respond(t(failed_key, ctx.lang, channel=label, folder=folder))
            return None

    async def file(self, event, ctx: CommandContext, action: ChannelRequestAction,
                   channel: ChannelInfo, invite_hash: str | None = None) -> None:
        """File a Channel request; a new one goes to the owner with Approve/Reject buttons."""
        filed, request = self.requests.file(ctx.user_id, action, channel, invite_hash)
        log.info("Channel request %s (%s) from user_id=%s: %s", request.id, action, ctx.user_id, filed)
        label = request_label(request, ctx.lang)
        if filed == Filed.ALREADY_PENDING:
            await event.respond(t("request_already_pending", ctx.lang, channel=label))
            return
        if filed == Filed.OTHER_PENDING:
            await event.respond(t("request_other_pending", ctx.lang, channel=label))
            return
        await event.respond(t("request_sent", ctx.lang, channel=label))
        if filed == Filed.NEW:
            owner = await self.client_commands.owner_id()
            if owner is None:
                log.warning("Channel request %s: nobody is owner to tell, it waits for /requests", request.id)
                return
            await self.send_request(owner, self._lang_of(owner), request)

    async def send_request(self, owner: int, lang: str, request: ChannelRequest) -> None:
        """Send the owner a pending request with its Approve/Reject buttons."""
        requesters = t("requesters_separator", lang).join(
            t("requester_username", lang, name=name) if name else t("requester_id", lang, id=user_id)
            for user_id, name in self.requests.requesters(request.id))
        text = t(f"request_owner_{request.action}", lang, requester=requesters, channel=request_label(request, lang))
        await self._send(owner, text, buttons=[[
            Button.inline(t("approve", lang), f"{Decision.APPROVE}:{request.id}"),
            Button.inline(t("reject", lang), f"{Decision.REJECT}:{request.id}"),
        ]])

    async def approve(self, event, owner: CommandContext, request_id: int) -> None:
        """Make the requested change; the request stays pending, and the owner hears why, if it fails."""
        async with self._decisions:
            request = self.requests.get(request_id)
            if request is None:
                await event.respond(t("request_already_decided", owner.lang))
                return
            log.info("Channel request %s (%s): approved", request.id, request.action)
            if request.action == ChannelRequestAction.ADD:
                label = await self.add(event, owner, request.identifier or "", request.invite_hash)
            else:
                label = await self.remove(event, owner, request.identifier)
            if label is None:
                await event.respond(t("request_still_pending", owner.lang))
                return
            # A request naming its channel was already answered when the channel's state changed
            await self._answer(request.id, lambda lang: t(f"request_approved_{request.action}", lang, channel=label))

    async def reject(self, request: ChannelRequest, label: str, reason: str) -> bool:
        """Close the request and send the requesters the reason; False if it was decided meanwhile."""
        async with self._decisions:
            answered = await self._answer(
                request.id, lambda lang: t("request_rejected_requester", lang, channel=label, reason=reason))
        if answered:
            log.info("Channel request %s (%s): rejected", request.id, request.action)
        return answered

    async def answer_requests(self, entered: dict[str, str], left: dict[str, str]) -> None:
        """Pending requests whose change happened, however it did, are done: requesters hear it.

        entered and left map the identifiers of channels that became or stopped being monitored to their labels.
        """
        done = {ChannelRequestAction.ADD: {i.lower(): label for i, label in entered.items()},
                ChannelRequestAction.REMOVE: {i.lower(): label for i, label in left.items()}}
        for request in self.requests.pending():
            identifier = request.identifier
            if identifier is None and entered:
                # An invite to a channel the account was not in: now it may be, and the invite names it
                invite = await self.client_commands.check_invite(request.invite_hash)
                identifier = invite and invite.identifier
            label = done[request.action].get((identifier or "").lower())
            if label is None:
                continue
            await self._answer(request.id, lambda lang, request=request, label=label:
                               t(f"request_approved_{request.action}", lang, channel=label))

    async def _answer(self, request_id: int, message: Callable[[str], str]) -> bool:
        """Close a decided request and send message(language) to each requester still authorized.

        False if it was already decided.
        """
        requesters = self.requests.close(request_id)
        if requesters is None:
            return False
        for user_id, lang in requesters:
            # Read now, not the list the bot started with: a user taken out of ALLOWED_USERS hears nothing
            if is_authorized(user_id, Config.ALLOWED_USERS, Config.ALLOW_ALL_USERS):
                await self._send(user_id, message(lang))
        return True

    async def _send(self, user_id: int, text: str, **kwargs) -> None:
        """Send a bot message; a user who never started or blocked the bot is logged, the others still hear."""
        try:
            await self.bot_client.send_message(user_id, text, **kwargs)
        except Exception as e:
            log.error("Error sending a bot message to %s: %s", user_id, e)

    def _lang_of(self, user_id: int) -> str:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            return resolve_lang(user and user.lang_code)
