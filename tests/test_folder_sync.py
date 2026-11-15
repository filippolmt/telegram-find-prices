"""
Tests for FolderSync: the Channel folder's channels are monitored for the owner.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telethon.tl.types import DialogFilter, InputPeerChannel, TextWithEntities
from telethon.tl.types.messages import DialogFilters

from client_commands import ClientCommands
from folder_sync import FolderSync
from models import User

OWNER = 100
CHANNELS = {
    1: SimpleNamespace(id=1, username="deals", title="Deals"),
    2: SimpleNamespace(id=2, username=None, title="Private deals"),
}


def _folder(*channel_ids, title="Offers", **flags):
    peers = [InputPeerChannel(channel_id=i, access_hash=0) for i in channel_ids]
    return DialogFilter(id=2, title=TextWithEntities(title, []), pinned_peers=[], include_peers=peers,
                        exclude_peers=[], **flags)


class FakeClient:
    """User client whose account has the given folders."""

    def __init__(self, *folders):
        self.folders = list(folders)

    async def get_me(self):
        return SimpleNamespace(id=OWNER)

    async def __call__(self, _request):
        return DialogFilters(filters=self.folders)

    async def get_entity(self, peer):
        return CHANNELS[peer.channel_id]


def _setup(db_session_factory, client, register_owner=True):
    if register_owner:
        with db_session_factory() as session:
            session.add(User(user_id=OWNER))
            session.commit()
    commands = ClientCommands(client, db_session_factory, MagicMock())
    commands.backfill_channel = AsyncMock(return_value=0)
    return commands, FolderSync(client, commands, db_session_factory, "Offers")


async def test_channel_entering_folder_is_linked_and_backfilled(db_session_factory):
    commands, sync = _setup(db_session_factory, FakeClient(_folder(1, 2)))

    await sync.sync()

    assert sorted(await commands.list_channels(OWNER)) == ["Deals (deals)", "Private deals (2)"]
    assert [c.args for c in commands.backfill_channel.await_args_list] == [("deals", OWNER), ("2", OWNER)]


async def test_channel_leaving_folder_is_unlinked(db_session_factory):
    client = FakeClient(_folder(1, 2))
    commands, sync = _setup(db_session_factory, client)
    await sync.sync()

    client.folders = [_folder(2)]
    await sync.sync()

    assert await commands.list_channels(OWNER) == ["Private deals (2)"]


async def test_channel_added_by_hand_stays_when_it_leaves_folder(db_session_factory):
    client = FakeClient(_folder(1))
    commands, sync = _setup(db_session_factory, client)
    await sync.sync()
    await commands.join_channel("deals", OWNER)

    client.folders = [_folder()]
    await sync.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]


async def test_folder_rule_flags_are_ignored_with_warning(db_session_factory, caplog):
    commands, sync = _setup(db_session_factory, FakeClient(_folder(1, broadcasts=True, groups=True)))

    await sync.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    assert "ignoring its rules (groups, broadcasts)" in caplog.text


async def test_unknown_folder_name_unlinks_nothing(db_session_factory, caplog):
    client = FakeClient(_folder(1))
    commands, sync = _setup(db_session_factory, client)
    await sync.sync()

    client.folders = [_folder(2, title="Renamed")]
    await sync.sync()

    assert await commands.list_channels(OWNER) == ["Deals (deals)"]
    assert "no folder named 'Offers'" in caplog.text


async def test_owner_not_registered_skips_sync(db_session_factory, caplog):
    commands, sync = _setup(db_session_factory, FakeClient(_folder(1)), register_owner=False)

    await sync.sync()

    assert await commands.list_channels(OWNER) == []
    commands.backfill_channel.assert_not_awaited()
    assert "send /start" in caplog.text
