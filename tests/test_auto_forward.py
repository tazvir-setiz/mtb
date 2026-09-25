from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.database.database import get_session
from app.database.models import ChannelType, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.telegram import auto_forward


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "skip", "failure"])
async def test_live_listener_records_shared_sender_outcome(monkeypatch, outcome):
    sender = AsyncMock(return_value=SimpleNamespace(id=99) if outcome == "success" else None)
    if outcome == "failure":
        sender.side_effect = ConnectionError("offline")
    monkeypatch.setattr(auto_forward, "send_message", sender)
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, -1, -1, 0).id
        SettingsRepository.set(session, "signature_text", "<b>sig</b>")

    event = SimpleNamespace(client=object(), message=SimpleNamespace(id=7))
    await auto_forward._on_new_message(event, -1001, -1002, job_id)
    sender.assert_awaited_once_with(event.client, event.message, -1001, -1002, "<b>sig</b>")
    with get_session() as session:
        record = ForwardedMessageRepository.recent(session)[0]
        assert (
            record.status
            == {
                "success": MessageStatus.SUCCESS,
                "skip": MessageStatus.SKIPPED,
                "failure": MessageStatus.FAILED,
            }[outcome]
        )
    if outcome == "success":
        await auto_forward._on_new_message(event, -1001, -1002, job_id)
        assert sender.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["source", "destination"])
async def test_confirm_channel_rebinds_live_forwarding(monkeypatch, kind):
    from app.handlers import dashboard, source
    from app.handlers.states import KEY_PENDING_CHANNEL

    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    client = SimpleNamespace(add_event_handler=Mock(), remove_event_handler=Mock())
    sender = AsyncMock(return_value=SimpleNamespace(id=99))
    monkeypatch.setattr(auto_forward, "send_message", sender)
    monkeypatch.setattr(source, "ensure_started", AsyncMock(return_value=client))
    monkeypatch.setattr(dashboard, "show_dashboard", AsyncMock())
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -1002, "Destination", ChannelType.DESTINATION)
    assert await auto_forward.enable(client)
    old_handler = auto_forward._handler
    context = SimpleNamespace(
        user_data={
            KEY_PENDING_CHANNEL: {
                "kind": kind,
                "telegram_id": -1003,
                "title": "New channel",
                "username": None,
                "message_id": 42,
            }
        }
    )
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            message=SimpleNamespace(message_id=42, reply_text=AsyncMock())
        )
    )
    await source.handle_confirm(update, context, kind)
    assert auto_forward.is_enabled()
    client.remove_event_handler.assert_called_once_with(old_handler)
    assert client.add_event_handler.call_count == 2
    event = SimpleNamespace(client=client, message=SimpleNamespace(id=7))
    # A callback already scheduled for the old listener must not use its old route.
    await old_handler(event)
    sender.assert_not_awaited()
    await auto_forward._handler(event)
    expected_source = -1003 if kind == "source" else -1001
    expected_destination = -1003 if kind == "destination" else -1002
    sender.assert_awaited_once_with(
        client, event.message, expected_source, expected_destination, None
    )


@pytest.mark.asyncio
async def test_failed_refresh_clears_enabled_state(monkeypatch):
    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    client = SimpleNamespace(add_event_handler=Mock(), remove_event_handler=Mock())
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -1002, "Destination", ChannelType.DESTINATION)
    await auto_forward.enable(client)
    old_handler = auto_forward._handler
    client.add_event_handler.side_effect = ConnectionError("offline")
    assert not await auto_forward.refresh_listener(client)
    assert not auto_forward.is_enabled()
    assert auto_forward._handler is None
    client.remove_event_handler.assert_called_once_with(old_handler)
