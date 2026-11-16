"""
In-memory stand-ins for Telethon events and the bot client, shared by bot command tests.
"""

import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from telethon import events
from telethon.errors import ChannelPrivateError, UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    GetDialogFiltersRequest,
    ImportChatInviteRequest,
    UpdateDialogFilterRequest,
)
from telethon.tl.types import (
    ChatInviteAlready,
    DialogFilter,
    InputPeerChannel,
    InputPeerUser,
    TextWithEntities,
)
from telethon.tl.types.messages import DialogFilters

import bot_commands
from bot_commands import BotCommands

OWNER = 100
FOLDER = "Offers"


def channel(id, username, title):
    return SimpleNamespace(id=id, username=username, title=title)


def peers(channel_ids):
    return [InputPeerChannel(channel_id=i, access_hash=0) for i in channel_ids]


def folder(*channel_ids, title=FOLDER, pinned=(), bots=(), **flags):
    """The DialogFilter of a folder listing these channels (and these bot users, which are not channels)."""
    return DialogFilter(id=2, title=TextWithEntities(title, []), pinned_peers=peers(pinned),
                        include_peers=peers(channel_ids) + [InputPeerUser(user_id=b, access_hash=0) for b in bots],
                        exclude_peers=[], **flags)


class FakeUserClient:
    """The owner's account at the Telethon boundary: its folders, the channels it can see and joins, the requests sent.

    `errors` maps a request type to the exception it raises; `owner` an exception makes get_me() raise it.
    """

    def __init__(self, *folders, owner=OWNER, channels=(), invites=None):
        self.folders = list(folders)
        self.owner = owner
        self.channels = {c.id: c for c in channels}
        self.invites = invites or {}  # invite hash -> channel
        self.joined = set()  # channel ids
        self.requests = []
        self.errors = {}

    async def get_me(self, input_peer=False):
        if isinstance(self.owner, BaseException):
            raise self.owner
        return SimpleNamespace(id=self.owner, user_id=self.owner)

    async def __call__(self, request):
        self.requests.append(request)
        if error := self.errors.get(type(request)):
            raise error
        if isinstance(request, GetDialogFiltersRequest):
            # Copies, as Telegram sends: a folder changes only through UpdateDialogFilterRequest
            return DialogFilters(filters=copy.deepcopy(self.folders))
        if isinstance(request, UpdateDialogFilterRequest):
            self.folders = [request.filter if f.id == request.id else f for f in self.folders]
        elif isinstance(request, JoinChannelRequest):
            self.joined.add((await self.get_entity(request.channel)).id)
        elif isinstance(request, LeaveChannelRequest):
            self.joined.discard((await self.get_entity(request.channel)).id)
        elif isinstance(request, ImportChatInviteRequest):
            chat = self.invites[request.hash]
            if chat.id in self.joined:
                raise UserAlreadyParticipantError(None)
            self.joined.add(chat.id)
            self.channels[chat.id] = chat
            return SimpleNamespace(chats=[chat])
        elif isinstance(request, CheckChatInviteRequest):
            chat = self.invites.get(request.hash) or channel(0, None, "Invited")
            return ChatInviteAlready(chat) if chat.id in self.joined else SimpleNamespace(title=chat.title)
        return True

    async def get_entity(self, peer):
        if isinstance(peer, str):
            # Telegram resolves usernames case-insensitively
            found = next((c for c in self.channels.values() if c.username and c.username.lower() == peer.lower()), None)
        else:
            found = self.channels.get(getattr(peer, "channel_id", peer))
        if found is None:
            raise ChannelPrivateError(None)
        return found

    async def get_input_entity(self, peer):
        return InputPeerChannel(channel_id=(await self.get_entity(peer)).id, access_hash=0)

    async def iter_messages(self, entity, limit, offset_id=0):
        return
        yield


def make_bot(monkeypatch, db_session_factory, allowed, allow_all):
    monkeypatch.setattr(bot_commands.Config, "ALLOWED_USERS", allowed)
    monkeypatch.setattr(bot_commands.Config, "ALLOW_ALL_USERS", allow_all)
    return BotCommands(MagicMock(), MagicMock(), db_session_factory)


def sender_event(user_id, username="stranger", lang="en", first_name="Stranger"):
    sender = SimpleNamespace(username=username, first_name=first_name, lang_code=lang)

    async def get_sender():
        return sender

    return SimpleNamespace(sender_id=user_id, get_sender=get_sender)


def chat_event(user_id, username="stranger", lang="en", first_name="Stranger"):
    event = sender_event(user_id, username, lang, first_name)
    event.replies = []

    async def respond(text):
        event.replies.append(text)

    event.respond = respond
    return event


def conversation_event(answers, user_id=1, username="owner", lang="en"):
    """A chat event whose conversation replies with `answers` in order: an exception instance is raised instead, a
    callable is called when the reply is awaited and its result is the reply."""
    event = chat_event(user_id, username, lang)
    event.chat_id = user_id
    answers = iter(answers)

    async def wait_event(_builder):
        answer = next(answers)
        if callable(answer):
            answer = answer()
        if isinstance(answer, BaseException):
            raise answer
        return SimpleNamespace(raw_text=answer)

    event.conversations = 0

    @asynccontextmanager
    async def conversation(_chat_id, timeout):
        event.conversations += 1
        yield SimpleNamespace(wait_event=wait_event)

    event.client = SimpleNamespace(conversation=conversation)
    return event


def button_event(data, answers=(), user_id=OWNER, username="owner", lang="en"):
    """A press of the inline button carrying `data`, in a chat whose conversation replies with `answers`."""
    event = conversation_event(answers, user_id, username, lang)
    event.data = data.encode()
    event.answers = []

    async def answer(text=None, alert=False):
        event.answers.append(text)

    event.answer = answer
    return event


class FakeBotClient:
    """Records handlers by event builder, as TelegramClient.on would, and the messages the bot sends."""

    def __init__(self):
        self.handlers = []
        self.sent = []  # (user_id, text, buttons)

    async def send_message(self, user_id, text, buttons=None, parse_mode=None):
        self.sent.append((user_id, text, buttons))

    def on(self, builder):
        def add(handler):
            self.handlers.append((builder, handler))
            return handler

        return add

    async def dispatch(self, text, event):
        event.raw_text = text
        matched = [h for b, h in self.handlers if isinstance(b, events.NewMessage) and b.pattern(text)]
        assert len(matched) == 1, f"{text!r} matched {len(matched)} handlers"
        await matched[0](event)

    async def press(self, event):
        matched = [h for b, h in self.handlers if isinstance(b, events.CallbackQuery) and b.match(event.data)]
        assert len(matched) == 1, f"{event.data!r} matched {len(matched)} handlers"
        await matched[0](event)

    def buttons_sent_to(self, user_id):
        """The data of every inline button sent to user_id, in order."""
        return [b.type.data.decode() for uid, _, rows in self.sent if uid == user_id for row in rows or () for b in row]


def registered_bot(monkeypatch, db_session_factory, bot_username="find_bot"):
    bot = make_bot(monkeypatch, db_session_factory, [1], False)
    bot.bot_client = FakeBotClient()
    bot.register_commands(bot_username)
    return bot
