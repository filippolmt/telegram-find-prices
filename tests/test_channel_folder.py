"""
Tests for ChannelFolder: the Channel folder's channels are monitored for the owner.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.errors import ChannelPrivateError
from telethon.tl.types import DialogFilter, InputPeerChannel, TextWithEntities
from telethon.tl.types.messages import DialogFilters

from bot_commands import BotCommands
from channel_folder import ChannelFolder
from client_commands import ClientCommands
from config import Config
from models import User
from tests.fakes import FakeBotClient, chat_event
from translations import t

OWNER = 100
CHANNELS = {
    1: SimpleNamespace(id=1, username="deals", title="Deals"),
    2: SimpleNamespace(id=2, username=None, title="Private deals"),
}


def _peers(channel_ids):
    return [InputPeerChannel(channel_id=i, access_hash=0) for i in channel_ids]


def _folder(*channel_ids, title="Offers", pinned=(), **flags):
    return DialogFilter(id=2, title=TextWithEntities(title, []), pinned_peers=_peers(pinned),
                        include_peers=_peers(channel_ids), exclude_peers=[], **flags)


class FakeClient:
    """User client whose account has the given folders."""

    def __init__(self, *folders):
        self.folders = list(folders)

    async def get_me(self):
        return SimpleNamespace(id=OWNER)

    async def __call__(self, _request):
        return DialogFilters(filters=self.folders)

    async def get_entity(self, peer):
        if isinstance(peer, str):
            # Telegram resolves usernames case-insensitively
            return next(c for c in CHANNELS.values() if c.username and c.username.lower() == peer.lower())
        if peer.channel_id not in CHANNELS:
            raise ChannelPrivateError(None)
        return CHANNELS[peer.channel_id]


def _setup(monkeypatch, db_session_factory, client, register_owner=True, allowed=(OWNER,)):
    monkeypatch.setattr(Config, "ALLOWED_USERS", list(allowed))
    monkeypatch.setattr(Config, "ALLOW_ALL_USERS", False)
    if register_owner:
        with db_session_factory() as session:
            session.add(User(user_id=OWNER))
            session.commit()
    commands = ClientCommands(client, db_session_factory, MagicMock())
    commands.backfill_channel = AsyncMock(return_value=0)
    return commands, ChannelFolder(client, commands, db_session_factory, "Offers")


async def test_channel_entering_folder_is_linked_and_backfilled(monkeypatch, db_session_factory):
    commands, folder = _setup(monkeypatch, db_session_factory, FakeClient(_folder(1, 2)))

    await folder.sync()

    assert sorted(await commands.list_channels(OWNER)) == ["Deals (deals)", "Private deals (2)"]
    assert [c.args for c in commands.backfill_channel.await_args_list] == [("deals", OWNER), ("2", OWNER)]


async def test_channel_leaving_folder_is_unlinked(monkeypatch, db_session_factory):
    client = FakeClient(_folder(1, 2))
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await folder.sync()

    client.folders = [_folder(2)]
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Private deals (2)"]


async def test_channel_added_by_hand_stays_when_it_leaves_folder(monkeypatch, db_session_factory):
    client = FakeClient(_folder(1))
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await folder.sync()
    await commands.join_channel("deals", OWNER)

    client.folders = [_folder()]
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]


async def test_folder_rule_flags_are_ignored_with_warning(monkeypatch, db_session_factory, caplog):
    commands, folder = _setup(monkeypatch, db_session_factory, FakeClient(_folder(1, broadcasts=True, groups=True)))

    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    assert "ignoring its rules (groups, broadcasts)" in caplog.text


async def test_unknown_folder_name_unlinks_nothing(monkeypatch, db_session_factory, caplog):
    client = FakeClient(_folder(1))
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await folder.sync()

    client.folders = [_folder(2, title="Renamed")]
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    assert "'Offers': the account has no folder with this name" in caplog.text


async def test_owner_not_registered_links_nothing(monkeypatch, db_session_factory, caplog):
    commands, folder = _setup(monkeypatch, db_session_factory, FakeClient(_folder(1)), register_owner=False)

    await folder.sync()

    assert await commands.list_channels(OWNER) == []
    commands.backfill_channel.assert_not_awaited()
    assert "send /start" in caplog.text


async def test_channel_added_by_hand_entering_folder_is_not_backfilled_again(monkeypatch, db_session_factory):
    client = FakeClient(_folder())
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await commands.join_channel("deals", OWNER)

    client.folders = [_folder(1)]
    await folder.sync()
    client.folders = [_folder()]
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    commands.backfill_channel.assert_not_awaited()


async def test_owner_no_longer_allowed_loses_folder_links_only(monkeypatch, db_session_factory, caplog):
    commands, folder = _setup(monkeypatch, db_session_factory, FakeClient(_folder(1, 2)))
    await folder.sync()
    await commands.join_channel("deals", OWNER)

    monkeypatch.setattr(Config, "ALLOWED_USERS", [OWNER + 1])
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    assert "not in ALLOWED_USERS" in caplog.text
async def test_channel_added_by_hand_in_other_case_is_one_channel(monkeypatch, db_session_factory):
    client = FakeClient(_folder())
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await commands.join_channel("Deals", OWNER)

    client.folders = [_folder(1)]
    await folder.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    commands.backfill_channel.assert_not_awaited()


async def test_channel_pinned_in_folder_counts(monkeypatch, db_session_factory):
    commands, folder = _setup(monkeypatch, db_session_factory, FakeClient(_folder(2, pinned=[1])))

    await folder.sync()

    assert sorted(await commands.list_channels(OWNER)) == ["Deals (deals)", "Private deals (2)"]


async def test_inaccessible_channel_is_skipped_and_unlinked(monkeypatch, db_session_factory, caplog):
    client = FakeClient(_folder(1))
    commands, folder = _setup(monkeypatch, db_session_factory, client)
    await folder.sync()

    monkeypatch.delitem(CHANNELS, 1)  # the account lost access, the channel is still in the folder
    await folder.sync()

    assert await commands.list_channels(OWNER) == []
    assert "skipping channel 1, no longer accessible" in caplog.text


def _bot_with_folder(monkeypatch, db_session_factory, client):
    commands, folder = _setup(monkeypatch, db_session_factory, client, register_owner=False, allowed=(OWNER, OWNER + 1))
    bot = BotCommands(FakeBotClient(), commands, db_session_factory, channel_folder=folder)
    bot.register_commands()
    return commands, bot


async def test_owner_start_reads_folder_at_once(monkeypatch, db_session_factory):
    commands, bot = _bot_with_folder(monkeypatch, db_session_factory, FakeClient(_folder(1, 2)))
    event = chat_event(OWNER, username="owner")

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", username="owner"),
                             t("folder_channels_monitored", "en", folder="Offers", count=2)]
    assert len(await commands.list_channels(OWNER)) == 2


async def test_other_user_start_leaves_folder_alone(monkeypatch, db_session_factory):
    commands, bot = _bot_with_folder(monkeypatch, db_session_factory, FakeClient(_folder(1, 2)))
    event = chat_event(OWNER + 1, username="friend")

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", username="friend")]
    assert await commands.list_channels(OWNER) == []
