from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.telegram import auto_forward, seen_chats
from app.telegram.bot import _remember_bot_membership
from app.telegram.channel_service import ChannelAccessError, resolve_channel
from app.telegram.client import BotClient
from app.ui.texts.channels import ask_channel


@pytest.fixture(autouse=True)
def _clean_seen_chats():
    seen_chats.clear()
    yield
    seen_chats.clear()


def _channel(chat_id=-1001234567890, title="کانال تست", username="test_channel", type_="channel"):
    return SimpleNamespace(id=chat_id, type=type_, title=title, username=username)


def _client(get_chat=None, member_status="administrator"):
    mock_bot = SimpleNamespace(
        get_chat=get_chat or AsyncMock(return_value=_channel()),
        get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status=member_status, can_post_messages=True)
        ),
    )
    return BotClient(mock_bot)


def test_record_and_find_by_id_and_username():
    entry = seen_chats.record(_channel())

    assert entry == {
        "id": -1001234567890,
        "title": "کانال تست",
        "username": "test_channel",
        "type": "channel",
    }
    assert seen_chats.find(-1001234567890)["title"] == "کانال تست"
    assert seen_chats.find("-1001234567890")["id"] == -1001234567890
    assert seen_chats.find("@test_channel")["id"] == -1001234567890
    assert seen_chats.find("test_channel")["id"] == -1001234567890
    assert seen_chats.recent(5)[0]["id"] == -1001234567890


def test_private_chats_are_not_recorded():
    assert seen_chats.record(SimpleNamespace(id=42, type="private", first_name="x")) is None
    assert seen_chats.recent(5) == []


def test_recording_twice_keeps_one_entry():
    seen_chats.record(_channel())
    seen_chats.record(_channel())
    assert len(seen_chats.recent(5)) == 1


def test_ask_channel_lists_seen_channels():
    seen_chats.record(_channel(title="منبع خبر", username=None))

    text = ask_channel("source", None, seen_chats.recent(5))

    assert "کانال‌هایی که ربات دیده است" in text
    assert "-1001234567890" in text
    assert "منبع خبر" in text


@pytest.mark.asyncio
async def test_resolve_falls_back_to_a_chat_the_bot_has_seen():
    seen_chats.record(_channel(chat_id=-100555, title="کانال دیده‌شده", username=None))
    client = _client(
        get_chat=AsyncMock(side_effect=BadRequest("Bad Request: chat not found"))
    )

    info = await resolve_channel(client, "-100555")

    assert info.telegram_id == -100555
    assert info.title == "کانال دیده‌شده"
    assert info.is_admin is True


@pytest.mark.asyncio
async def test_resolve_still_fails_for_unknown_chat():
    client = _client(
        get_chat=AsyncMock(side_effect=BadRequest("Bad Request: chat not found"))
    )

    with pytest.raises(ChannelAccessError):
        await resolve_channel(client, "-100999")


@pytest.mark.asyncio
async def test_channel_post_records_seen_chat_even_when_forwarding_is_disabled(monkeypatch):
    monkeypatch.setattr(auto_forward, "is_enabled", lambda: False)
    chat = _channel(chat_id=-100777, title="منبع", username=None)
    update = SimpleNamespace(
        effective_chat=chat,
        channel_post=SimpleNamespace(chat_id=-100777),
        message=None,
        effective_message=None,
    )

    await auto_forward.handle_channel_update(update, None)

    assert seen_chats.find(-100777)["title"] == "منبع"


@pytest.mark.asyncio
async def test_my_chat_member_update_records_the_channel():
    chat = _channel(chat_id=-100888, title="کانال تازه", username=None)
    update = SimpleNamespace(my_chat_member=SimpleNamespace(chat=chat))

    await _remember_bot_membership(update, None)

    assert seen_chats.find(-100888)["title"] == "کانال تازه"
