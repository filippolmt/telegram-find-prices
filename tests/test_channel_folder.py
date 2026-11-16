"""
Tests for ChannelFolder: with a Channel folder, it holds exactly the monitored channels.
"""

from unittest.mock import AsyncMock, MagicMock

from bot_commands import BotCommands
from channel_folder import ChannelFolder
from client_commands import ClientCommands
from config import Config
from tests.fakes import (
    FOLDER,
    OWNER,
    FakeBotClient,
    FakeUserClient,
    channel,
    chat_event,
    folder,
)
from translations import t

DEALS = channel(1, "deals", "Deals")
PRIVATE = channel(2, None, "Private deals")


def _setup(db_session_factory, client):
    client.channels = {c.id: c for c in (DEALS, PRIVATE)}
    commands = ClientCommands(client, db_session_factory, MagicMock())
    commands.backfill_channel = AsyncMock(return_value=0)
    return commands, ChannelFolder(client, commands, FOLDER)


async def test_channel_entering_folder_is_monitored_and_backfilled(db_session_factory):
    commands, channel_folder = _setup(db_session_factory, FakeUserClient(folder(1, 2)))

    await channel_folder.sync()

    assert commands.list_channels() == ["Deals (deals)", "Private deals (2)"]
    assert [c.args for c in commands.backfill_channel.await_args_list] == [("deals",), ("2",)]


async def test_channel_leaving_folder_stops_being_monitored_and_account_stays_in_it(db_session_factory):
    client = FakeUserClient(folder(1, 2))
    commands, channel_folder = _setup(db_session_factory, client)
    await channel_folder.sync()

    client.folders = [folder(2)]
    await channel_folder.sync()

    assert commands.list_channels() == ["Private deals (2)"]
    assert not [r for r in client.requests if type(r).__name__ == "LeaveChannelRequest"]


async def test_folder_rule_flags_are_ignored_with_warning(db_session_factory, caplog):
    commands, channel_folder = _setup(db_session_factory, FakeUserClient(folder(1, broadcasts=True, groups=True)))

    await channel_folder.sync()

    assert commands.list_channels() == ["Deals (deals)"]
    assert "ignoring its rules (groups, broadcasts)" in caplog.text


async def test_unknown_folder_name_changes_nothing(db_session_factory, caplog):
    client = FakeUserClient(folder(1))
    commands, channel_folder = _setup(db_session_factory, client)
    await channel_folder.sync()

    client.folders = [folder(2, title="Renamed")]
    await channel_folder.sync()

    assert commands.list_channels() == ["Deals (deals)"]
    assert "'Offers': the account has no folder with this name" in caplog.text


async def test_monitored_channel_entering_folder_is_not_backfilled_again(db_session_factory):
    client = FakeUserClient(folder())
    commands, channel_folder = _setup(db_session_factory, client)
    commands.monitor("Deals", None)  # stored as typed before join_channel() kept Telegram's spelling

    client.folders = [folder(1)]
    await channel_folder.sync()

    assert commands.list_channels() == ["Deals (Deals)"]
    commands.backfill_channel.assert_not_awaited()


async def test_channel_pinned_in_folder_counts(db_session_factory):
    commands, channel_folder = _setup(db_session_factory, FakeUserClient(folder(2, pinned=[1])))

    await channel_folder.sync()

    assert commands.list_channels() == ["Deals (deals)", "Private deals (2)"]


async def test_inaccessible_channel_is_skipped_and_no_longer_monitored(db_session_factory, caplog):
    client = FakeUserClient(folder(1))
    commands, channel_folder = _setup(db_session_factory, client)
    await channel_folder.sync()

    del client.channels[1]  # the account lost access, the channel is still in the folder
    await channel_folder.sync()

    assert commands.list_channels() == []
    assert "skipping channel 1, no longer accessible" in caplog.text


def _bot_with_folder(db_session_factory, client):
    Config.ALLOWED_USERS = [OWNER, OWNER + 1]  # restored by the every_user_allowed fixture
    commands, channel_folder = _setup(db_session_factory, client)
    bot = BotCommands(FakeBotClient(), commands, db_session_factory, channel_folder=channel_folder)
    bot.register_commands()
    return commands, bot


async def test_owner_start_reads_folder_at_once(db_session_factory):
    commands, bot = _bot_with_folder(db_session_factory, FakeUserClient(folder(1, 2)))
    event = chat_event(OWNER, username="owner")

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", name="owner"),
                             t("folder_channels_monitored", "en", folder=FOLDER, count=2)]
    assert len(commands.list_channels()) == 2


async def test_other_user_start_leaves_folder_alone(db_session_factory):
    commands, bot = _bot_with_folder(db_session_factory, FakeUserClient(folder(1, 2)))
    event = chat_event(OWNER + 1, username="friend")

    await bot.bot_client.dispatch("/start", event)

    assert event.replies == [t("welcome", "en", name="friend")]
    assert commands.list_channels() == []
