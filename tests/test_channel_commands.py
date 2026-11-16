"""
Monitored channels are shared and chosen by the owner: the owner's channel commands, other users' Channel requests
and the owner's Approve/Reject buttons, through the registered commands and a fake owner's account.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
from telethon.errors import RPCError
from telethon.tl.functions.messages import UpdateDialogFilterRequest

from bot_commands import BotCommands
from channel_folder import ChannelFolder
from client_commands import ClientCommands
from config import Config
from models import User
from tests.fakes import (
    FOLDER,
    OWNER,
    FakeBotClient,
    FakeUserClient,
    button_event,
    channel,
    conversation_event,
    folder,
)
from translations import t

FRIEND = 200
OTHER = 300
DEALS = channel(1, "deals", "Deals")
TECH = channel(2, "tech", "Tech offers")
PRIVATE = channel(3, None, "Private deals")


@pytest.fixture
def setup(monkeypatch, db_session_factory):
    """Build the bot over a fake owner's account, with or without a Channel folder."""
    monkeypatch.setattr(Config, "ALLOWED_USERS", [OWNER, FRIEND, OTHER])
    monkeypatch.setattr(Config, "ALLOW_ALL_USERS", False)
    with db_session_factory() as session:
        session.add_all([User(id=uid, user_id=uid, username=name)
                         for uid, name in ((OWNER, "owner"), (FRIEND, "friend"), (OTHER, "other"))])
        session.commit()

    def build(*folders, with_folder=True, **client_args):
        client = FakeUserClient(*folders, channels=(DEALS, TECH, PRIVATE), **client_args)
        bot_client = FakeBotClient()
        commands = ClientCommands(client, db_session_factory, bot_client)
        commands.backfill_channel = AsyncMock(return_value=0)
        channel_folder = ChannelFolder(client, commands, FOLDER) if with_folder else None
        bot = BotCommands(bot_client, commands, db_session_factory, channel_folder)
        bot.register_commands()
        return bot, client

    return build


async def test_owner_add_channel_without_folder_joins_monitors_and_backfills(setup):
    bot, client = setup(with_folder=False)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert client.joined == {DEALS.id}
    assert bot.client_commands.list_channels() == ["Deals (deals)"]
    bot.client_commands.backfill_channel.assert_awaited_once_with("deals")
    assert event.replies == [t("channel_added", "en", channel="Deals (deals)"),
                             t("scanning_messages", "en"), t("backfill_no_matches", "en")]


async def test_user_add_channel_without_folder_is_refused(setup):
    bot, client = setup(with_folder=False)
    event = conversation_event([], user_id=FRIEND, username="friend")

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert event.replies == [t("channels_owner_only", "en")]
    assert client.joined == set()
    assert bot.client_commands.list_channels() == []


async def test_nobody_is_owner_when_the_account_cannot_be_read(setup):
    bot, client = setup(with_folder=False, owner=ConnectionError("offline"))
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert event.replies == [t("channels_owner_only", "en")]
    assert client.joined == set()


async def test_owner_add_channel_with_folder_puts_it_in_the_folder_keeping_the_rest(setup):
    original = folder(2, pinned=[3], bots=[999], color=4, emoticon="🛒")
    bot, client = setup(original)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @deals", event)

    [written] = client.folders
    assert [p.channel_id for p in written.include_peers if hasattr(p, "channel_id")] == [2, 1]
    assert [p.user_id for p in written.include_peers if hasattr(p, "user_id")] == [999]
    assert ([p.channel_id for p in written.pinned_peers], written.color, written.emoticon, written.title.text) == \
        ([3], 4, "🛒", FOLDER)
    assert client.joined == {DEALS.id}
    assert bot.client_commands.list_channels() == ["Deals (deals)"]
    bot.client_commands.backfill_channel.assert_awaited_once_with("deals")


async def test_owner_add_channel_to_a_full_folder_says_the_account_joined_but_it_is_not_monitored(setup):
    bot, client = setup(folder(2))
    client.errors[UpdateDialogFilterRequest] = RPCError(None, "FILTER_INCLUDE_TOO_MUCH", 400)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert event.replies == [t("folder_add_failed", "en", channel="Deals (deals)", folder=FOLDER)]
    assert client.joined == {DEALS.id}
    assert bot.client_commands.list_channels() == []
    bot.client_commands.backfill_channel.assert_not_awaited()


async def test_owner_remove_channel_takes_it_out_of_the_folder_and_leaves_it(setup):
    bot, client = setup(folder(1, 2, bots=[999]))
    await bot.channel_folder.sync()
    client.joined = {DEALS.id, TECH.id}
    event = conversation_event(["1"], user_id=OWNER)

    await bot.bot_client.dispatch("/remove_channel", event)

    assert event.replies == [t("remove_channel_prompt", "en", items="1. Deals (deals)\n2. Tech offers (tech)"),
                             t("channel_removed", "en", channel="Deals (deals)")]
    assert [getattr(p, "channel_id", getattr(p, "user_id", None)) for p in client.folders[0].include_peers] == [2, 999]
    assert client.joined == {TECH.id}
    assert bot.client_commands.list_channels() == ["Tech offers (tech)"]


async def test_owner_remove_channel_without_folder_leaves_it(setup):
    bot, client = setup(with_folder=False)
    await bot.bot_client.dispatch("/add_channel @deals", conversation_event([], user_id=OWNER))
    event = conversation_event(["1"], user_id=OWNER)

    await bot.bot_client.dispatch("/remove_channel", event)

    assert event.replies[-1] == t("channel_removed", "en", channel="Deals (deals)")
    assert client.joined == set()
    assert bot.client_commands.list_channels() == []


async def test_user_add_channel_with_folder_files_a_request_for_the_owner(setup):
    bot, client = setup(folder())
    event = conversation_event([], user_id=FRIEND, username="friend")

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert event.replies == [t("request_sent", "en", channel="deals")]
    assert client.joined == set()
    assert [(uid, text) for uid, text, _ in bot.bot_client.sent] == [
        (OWNER, t("request_owner_add", "en", requester="@friend", channel="deals"))]
    assert bot.bot_client.buttons_sent_to(OWNER) == ["approve:1", "reject:1"]


async def test_user_add_channel_already_monitored_files_nothing(setup):
    bot, _ = setup(folder(1))
    await bot.channel_folder.sync()
    event = conversation_event([], user_id=FRIEND, username="friend")

    await bot.bot_client.dispatch("/add_channel @Deals", event)

    assert event.replies == [t("channel_already_monitored", "en", channel="Deals (deals)")]
    assert bot.bot_client.sent == []


async def test_one_pending_request_per_channel(setup):
    bot, _ = setup(folder(2))
    await bot.channel_folder.sync()
    replies = []
    for user_id, command in ((FRIEND, "/add_channel @deals"), (OTHER, "/add_channel deals"),
                             (FRIEND, "/add_channel @deals"), (FRIEND, "/remove_channel"), (OTHER, "/remove_channel")):
        event = conversation_event(["1"], user_id=user_id)
        await bot.bot_client.dispatch(command, event)
        replies.append(event.replies[-1])


    assert replies == [
        t("request_sent", "en", channel="deals"),
        t("request_sent", "en", channel="deals"),  # joins FRIEND's request: no second message to the owner
        t("request_already_pending", "en", channel="deals"),
        t("request_sent", "en", channel="Tech offers (tech)"),
        t("request_sent", "en", channel="Tech offers (tech)"),
    ]
    assert bot.bot_client.buttons_sent_to(OWNER) == ["approve:1", "reject:1", "approve:2", "reject:2"]


async def _request(bot, command, *users, answers=()):
    for user_id in users:
        username = {FRIEND: "friend", OTHER: "other"}[user_id]
        await bot.bot_client.dispatch(command, conversation_event(list(answers), user_id=user_id, username=username))
    bot.bot_client.sent.clear()


async def test_owner_approves_add_request(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel https://t.me/+InviteHash123", FRIEND, OTHER)
    client.invites["InviteHash123"] = DEALS
    event = button_event("approve:1")

    await bot.bot_client.press(event)

    assert client.joined == {DEALS.id}
    assert [p.channel_id for p in client.folders[0].include_peers] == [2, 1]
    assert bot.client_commands.list_channels() == ["Deals (deals)"]
    bot.client_commands.backfill_channel.assert_awaited_once_with("deals")
    assert event.replies[0] == t("channel_added", "en", channel="Deals (deals)")
    assert bot.bot_client.sent == [(uid, t("request_approved_add", "en", channel="Deals (deals)"), None)
                                   for uid in (FRIEND, OTHER)]
    assert bot.channel_requests.pending() == []


async def test_button_pressed_by_another_account_is_refused(setup, caplog):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)
    event = button_event("approve:1", user_id=FRIEND)

    await bot.bot_client.press(event)

    assert event.answers == [t("owner_only_button", "en")]
    assert client.joined == set()
    assert [r.id for r in bot.channel_requests.pending()] == [1]
    assert "pressed by user_id=200, not the owner" in caplog.text


async def test_owner_rejects_with_a_reason_the_requesters_get(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)
    event = button_event("reject:1", answers=["Too many ads"])

    await bot.bot_client.press(event)

    assert event.replies == [t("reject_reason_prompt", "en", channel="deals"), t("request_rejected", "en", channel="deals")]
    assert bot.bot_client.sent == [(FRIEND, t("request_rejected_requester", "en", channel="deals", reason="Too many ads"), None)]
    assert client.joined == set()
    assert bot.channel_requests.pending() == []


async def test_reject_cancelled_or_without_reason_leaves_the_request_pending(setup):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)
    cancelled, empty = button_event("reject:1", answers=["/cancel"]), button_event("reject:1", answers=[""])

    await bot.bot_client.press(cancelled)
    await bot.bot_client.press(empty)

    assert cancelled.replies[-1] == t("operation_cancelled", "en")
    assert empty.replies[-1] == t("reject_reason_required", "en")
    assert bot.bot_client.sent == []
    assert [r.id for r in bot.channel_requests.pending()] == [1]


async def test_approval_failing_on_the_folder_leaves_the_request_pending(setup):
    bot, client = setup()  # the folder is missing
    await _request(bot, "/add_channel @deals", FRIEND)
    event = button_event("approve:1")

    await bot.bot_client.press(event)

    assert event.replies == [t("folder_add_failed", "en", channel="Deals (deals)", folder=FOLDER),
                             t("request_still_pending", "en")]
    assert client.joined == {DEALS.id}  # reported to the owner, not left silently
    assert bot.client_commands.list_channels() == []
    assert bot.bot_client.sent == []
    assert [r.id for r in bot.channel_requests.pending()] == [1]


async def test_owner_approves_remove_request(setup):
    bot, client = setup(folder(1, 2))
    await bot.channel_folder.sync()
    client.joined = {DEALS.id, TECH.id}
    await _request(bot, "/remove_channel", FRIEND, answers=["1"])
    event = button_event("approve:1")

    await bot.bot_client.press(event)

    assert [p.channel_id for p in client.folders[0].include_peers] == [2]
    assert client.joined == {TECH.id}
    assert bot.client_commands.list_channels() == ["Tech offers (tech)"]
    assert bot.bot_client.sent == [(FRIEND, t("request_approved_remove", "en", channel="Deals (deals)"), None)]


async def test_requests_lists_pending_ones_to_the_owner_with_their_buttons(setup):
    bot, _ = setup(folder(2))
    await bot.channel_folder.sync()
    await _request(bot, "/add_channel @deals", FRIEND)
    await _request(bot, "/remove_channel", OTHER, answers=["1"])
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/requests", event)

    assert [(uid, text) for uid, text, _ in bot.bot_client.sent] == [
        (OWNER, t("request_owner_add", "en", requester="@friend", channel="deals")),
        (OWNER, t("request_owner_remove", "en", requester="@other", channel="Tech offers (tech)")),
    ]
    assert bot.bot_client.buttons_sent_to(OWNER) == ["approve:1", "reject:1", "approve:2", "reject:2"]


async def test_requests_is_for_the_owner_only(setup):
    bot, _ = setup(folder())
    event = conversation_event([], user_id=FRIEND)

    await bot.bot_client.dispatch("/requests", event)

    assert event.replies == [t("channels_owner_only", "en")]


async def test_list_channels_shows_every_monitored_channel_and_own_pending_requests(setup):
    bot, _ = setup(folder(2))
    await bot.channel_folder.sync()
    await _request(bot, "/add_channel @deals", FRIEND)
    await _request(bot, "/add_channel @news_it", OTHER)
    event = conversation_event([], user_id=FRIEND)

    await bot.bot_client.dispatch("/list_channels", event)

    assert event.replies == [t("monitored_channels", "en", channels="Tech offers (tech)")
                             + t("your_pending_requests", "en", requests="+ deals")]


async def test_a_requester_who_blocked_the_bot_does_not_stop_the_others_hearing(setup):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND, OTHER)
    send = bot.bot_client.send_message

    async def blocked_by_friend(user_id, text, **kwargs):
        if user_id == FRIEND:
            raise RPCError(None, "USER_IS_BLOCKED", 400)
        await send(user_id, text, **kwargs)

    bot.bot_client.send_message = blocked_by_friend
    await bot.bot_client.press(button_event("reject:1", answers=["Too many ads"]))

    assert bot.bot_client.sent == [(OTHER, t("request_rejected_requester", "en", channel="deals", reason="Too many ads"), None)]


async def test_owner_adding_a_requested_channel_answers_the_pending_request(setup):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)

    await bot.bot_client.dispatch("/add_channel @deals", conversation_event([], user_id=OWNER))

    assert bot.bot_client.sent == [(FRIEND, t("request_approved_add", "en", channel="Deals (deals)"), None)]
    assert bot.channel_requests.pending() == []


async def test_requested_channel_entering_the_folder_by_hand_answers_the_pending_request(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)

    client.folders = [folder(1, 2)]  # the owner moved it in from Telegram
    await bot.channel_folder.sync()

    assert bot.bot_client.sent == [(FRIEND, t("request_approved_add", "en", channel="Deals (deals)"), None)]
    assert bot.channel_requests.pending() == []


async def test_approval_failing_on_any_folder_error_tells_the_owner(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)

    async def unresolvable(_peer):
        raise ValueError("Could not find the input entity")

    client.get_input_entity = unresolvable
    event = button_event("approve:1")
    await bot.bot_client.press(event)

    assert event.replies == [t("folder_add_failed", "en", channel="Deals (deals)", folder=FOLDER),
                             t("request_still_pending", "en")]
    assert [r.id for r in bot.channel_requests.pending()] == [1]


async def test_account_is_not_owner_when_only_allow_all_users_lets_it_in(setup, monkeypatch):
    bot, client = setup(with_folder=False)
    monkeypatch.setattr(Config, "ALLOWED_USERS", [])
    monkeypatch.setattr(Config, "ALLOW_ALL_USERS", True)
    event = conversation_event([], user_id=OWNER)

    await bot.bot_client.dispatch("/add_channel @deals", event)

    assert event.replies == [t("channels_owner_only", "en")]
    assert client.joined == set()


async def test_reject_of_a_request_decided_meanwhile_is_not_reported_as_rejected(setup):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)

    def approved_while_typing():
        bot.channel_requests.close(1)
        return "Too many ads"

    event = button_event("reject:1", answers=[approved_while_typing])
    await bot.bot_client.press(event)

    assert event.replies[-1] == t("request_already_decided", "en")
    assert bot.bot_client.sent == []


async def test_invite_and_username_requests_for_one_channel_are_both_answered(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel https://t.me/+InviteHash123", FRIEND)
    await _request(bot, "/add_channel @deals", OTHER)
    client.invites["InviteHash123"] = DEALS

    await bot.bot_client.press(button_event("approve:1"))

    assert sorted(uid for uid, _, _ in bot.bot_client.sent) == [FRIEND, OTHER]
    assert bot.channel_requests.pending() == []


async def test_channel_taken_out_of_the_folder_by_hand_answers_its_pending_remove_request(setup):
    bot, client = setup(folder(1, 2))
    await bot.channel_folder.sync()
    client.joined = {DEALS.id, TECH.id}
    await _request(bot, "/remove_channel", FRIEND, answers=["1"])

    client.folders = [folder(2)]  # the owner took it out from Telegram, keeping the account in it
    await bot.channel_folder.sync()

    assert bot.bot_client.sent == [(FRIEND, t("request_approved_remove", "en", channel="Deals (deals)"), None)]
    assert bot.channel_requests.pending() == []
    assert client.joined == {DEALS.id, TECH.id}


async def test_owner_removing_a_requested_channel_answers_the_pending_remove_request(setup):
    bot, _ = setup(folder(1, 2))
    await bot.channel_folder.sync()
    await _request(bot, "/remove_channel", FRIEND, answers=["1"])

    await bot.bot_client.dispatch("/remove_channel", conversation_event(["1"], user_id=OWNER))

    assert bot.bot_client.sent == [(FRIEND, t("request_approved_remove", "en", channel="Deals (deals)"), None)]
    assert bot.channel_requests.pending() == []


async def test_folder_is_not_read_while_nobody_is_owner(setup, monkeypatch):
    bot, client = setup(folder(1))
    await bot.channel_folder.sync()
    monkeypatch.setattr(Config, "ALLOWED_USERS", [FRIEND])  # the account is no longer listed

    client.folders = [folder(2)]
    await bot.channel_folder.sync()

    assert bot.client_commands.list_channels() == ["Deals (deals)"]


async def test_reject_is_refused_if_the_account_is_no_longer_owner_when_the_reason_arrives(setup, monkeypatch):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)

    def owner_removed_while_typing():
        monkeypatch.setattr(Config, "ALLOWED_USERS", [FRIEND, OTHER])
        return "Too many ads"

    event = button_event("reject:1", answers=[owner_removed_while_typing])
    await bot.bot_client.press(event)

    assert event.replies[-1] == t("owner_only_button", "en")
    assert bot.bot_client.sent == []
    assert [r.id for r in bot.channel_requests.pending()] == [1]


async def test_concurrent_approvals_of_one_request_act_once(setup):
    bot, client = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND)
    first, second = button_event("approve:1"), button_event("approve:1")

    await asyncio.gather(bot.bot_client.press(first), bot.bot_client.press(second))

    assert sum(type(r).__name__ == "JoinChannelRequest" for r in client.requests) == 1
    assert (first.replies + second.replies).count(t("request_already_decided", "en")) == 1


async def test_owner_add_channel_is_refused_if_the_account_is_no_longer_owner_when_the_channel_arrives(setup, monkeypatch):
    bot, client = setup(folder(2))

    def owner_removed_while_typing():
        monkeypatch.setattr(Config, "ALLOWED_USERS", [FRIEND, OTHER])
        return "@deals"

    event = conversation_event([owner_removed_while_typing], user_id=OWNER)
    await bot.bot_client.dispatch("/add_channel", event)

    assert event.replies[-1] == t("channels_owner_only", "en")
    assert client.joined == set()


async def test_requester_no_longer_authorized_gets_no_answer(setup, monkeypatch):
    bot, _ = setup(folder(2))
    await _request(bot, "/add_channel @deals", FRIEND, OTHER)
    monkeypatch.setattr(Config, "ALLOWED_USERS", [OWNER, OTHER])

    await bot.bot_client.press(button_event("approve:1"))

    assert [uid for uid, _, _ in bot.bot_client.sent] == [OTHER]
