from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import load_settings
from app.database.database import get_session
from app.database.models import ChannelType, ForwardedMessage, MessageStatus
from app.database.repository import ChannelRepository
from app.services.statistics_service import get_system_health_report
from app.telegram import auto_forward
from app.telegram.bot import build_application
from app.telegram.channel_service import (
    ChannelAccessError,
    normalize_channel_ref,
    resolve_channel,
    verify_destination_permissions,
)
from app.telegram.client import BotClient, BotMessage


def test_platform_settings_default_telegram(monkeypatch):
    monkeypatch.delenv("PLATFORM", raising=False)
    monkeypatch.delenv("BOT_PLATFORM", raising=False)
    monkeypatch.setenv("BOT_TOKEN", "123:test_tok")
    s = load_settings()
    assert s.platform == "telegram"
    assert s.bot_base_url == "https://api.telegram.org/bot"
    assert s.bot_base_file_url == "https://api.telegram.org/file/bot"


def test_platform_settings_bale(monkeypatch):
    monkeypatch.setenv("PLATFORM", "bale")
    monkeypatch.setenv("BOT_TOKEN", "123:bale_tok")
    s = load_settings()
    assert s.platform == "bale"
    assert s.bot_base_url == "https://tapi.bale.ai/bot"
    assert s.bot_base_file_url == "https://tapi.bale.ai/file/bot"


def test_bale_application_builder(monkeypatch):
    monkeypatch.setenv("PLATFORM", "bale")
    monkeypatch.setenv("BOT_TOKEN", "123:bale_tok")
    from app import config

    monkeypatch.setattr(config, "settings", load_settings())
    import app.telegram.bot as bot_module

    monkeypatch.setattr(bot_module, "settings", config.settings)

    app = build_application()
    assert "tapi.bale.ai" in app.bot.base_url


@pytest.mark.asyncio
async def test_unsupported_profile_method_does_not_abort_startup():
    """Bale answers unknown methods with ``InvalidToken: Handler not found``."""
    from telegram.error import InvalidToken

    from app.telegram import bot_profile

    bot = SimpleNamespace(
        set_my_commands=AsyncMock(),
        set_chat_menu_button=AsyncMock(side_effect=InvalidToken("Handler not found")),
        set_my_short_description=AsyncMock(),
        set_my_description=AsyncMock(),
    )

    await bot_profile.setup_bot_ui(bot)

    bot.set_my_commands.assert_awaited_once()
    bot.set_my_short_description.assert_awaited_once()
    bot.set_my_description.assert_awaited_once()


def test_normalize_channel_ref_bale():
    assert normalize_channel_ref("https://ble.ir/my_bale_channel") == "@my_bale_channel"
    assert normalize_channel_ref("https://ble.ir/news_channel/123/456") == "@news_channel"
    assert normalize_channel_ref("@bale_group") == "@bale_group"
    assert normalize_channel_ref("-100987654321") == -100987654321


@pytest.mark.asyncio
async def test_bot_client_cache_and_get_messages():
    mock_bot = SimpleNamespace()
    client = BotClient(mock_bot)

    assert client.is_connected() is False
    await client.connect()
    assert client.is_connected() is True
    assert await client.is_user_authorized() is True

    # Cache message
    msg = BotMessage(message_id=42, text="Salam Bale", chat_id=-1001)
    client.cache_message(-1001, msg)

    messages = await client.get_messages(-1001, [42, 99])
    assert len(messages) == 2
    assert messages[0].id == 42
    assert messages[0].text == "Salam Bale"
    assert messages[1].id == 99


@pytest.mark.asyncio
async def test_bot_client_send_and_copy_message():
    mock_bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=101)),
        send_photo=AsyncMock(return_value=SimpleNamespace(message_id=102)),
        copy_message=AsyncMock(return_value=SimpleNamespace(message_id=103)),
        forward_message=AsyncMock(return_value=SimpleNamespace(message_id=104)),
    )
    client = BotClient(mock_bot)

    # Text message
    res = await client.send_message(-2001, "Test text")
    assert res.message_id == 101
    mock_bot.send_message.assert_awaited_once()

    # Photo message
    res = await client.send_message(-2001, "Caption", file="photo_file_id")
    assert res.message_id == 102
    mock_bot.send_photo.assert_awaited_once()

    # Copy message
    res = await client.copy_message(-2001, -1001, 42, caption="New caption")
    assert res.message_id == 103
    mock_bot.copy_message.assert_awaited_once()

    # Forward message (with drop_author=False)
    res = await client.forward_messages(-2001, 42, -1001, drop_author=False)
    assert res.message_id == 104
    mock_bot.forward_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_channel_and_verify_permissions_via_bot():
    mock_bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=-100111,
                title="Bale Source Channel",
                username="bale_source",
                type="channel",
            )
        ),
        get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status="administrator", can_post_messages=True)
        ),
    )
    client = BotClient(mock_bot)

    info = await resolve_channel(client, "@bale_source")
    assert info.telegram_id == -100111
    assert info.title == "Bale Source Channel"
    assert info.username == "bale_source"
    assert info.is_admin is True
    assert info.can_post is True

    # Should pass permission verification
    verified = await verify_destination_permissions(client, "@bale_source")
    assert verified.telegram_id == -100111

    # Non-admin failure
    mock_bot.get_chat_member = AsyncMock(
        return_value=SimpleNamespace(status="member", can_post_messages=False)
    )
    with pytest.raises(ChannelAccessError, match="Administrator"):
        await verify_destination_permissions(client, "@bale_source")


@pytest.mark.asyncio
async def test_handle_channel_update_end_to_end(monkeypatch):
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source Channel", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -2001, "Destination Channel", ChannelType.DESTINATION)

    mock_bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=555)),
        copy_message=AsyncMock(return_value=SimpleNamespace(message_id=556)),
    )
    client = BotClient(mock_bot)
    await auto_forward.enable(client)

    # Incoming update from channel
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(id=-1001),
        channel_post=SimpleNamespace(
            message_id=88,
            id=88,
            text="Breaking News from Bale/Telegram",
            text_html="Breaking News from Bale/Telegram",
            entities=[],
            photo=[],
            video=None,
            document=None,
            audio=None,
            voice=None,
            animation=None,
            poll=None,
            media=None,
        ),
        message=None,
        effective_message=None,
    )
    context = SimpleNamespace(bot=mock_bot)

    await auto_forward.handle_channel_update(update, context)

    # Check that message was delivered and recorded
    with get_session() as session:
        records = session.query(ForwardedMessage).all()
        assert len(records) == 1
        assert records[0].source_channel_id == -1001
        assert records[0].destination_channel_id == -2001
        assert records[0].source_message_id == 88
        assert records[0].status == MessageStatus.SUCCESS

    await auto_forward.disable(client)


@pytest.mark.asyncio
async def test_bale_health_report(monkeypatch):
    from dataclasses import replace

    from app import config
    from app.services import statistics_service

    bale_settings = replace(config.settings, platform="bale")
    monkeypatch.setattr(config, "settings", bale_settings)
    monkeypatch.setattr(statistics_service, "settings", bale_settings)

    mock_client = SimpleNamespace(
        is_connected=lambda: True,
        is_user_authorized=AsyncMock(return_value=True),
        get_me=AsyncMock(
            return_value=SimpleNamespace(id=12345, first_name="BaleBot", username="my_bale_bot")
        ),
    )
    monkeypatch.setattr("app.services.statistics_service.get_client", lambda: mock_client)

    report = await get_system_health_report()
    assert "بله (Bale)" in report
    assert "BaleBot" in report
    assert "سلامت سیستم" in report
