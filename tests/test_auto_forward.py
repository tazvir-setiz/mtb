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
async def test_listener_forwards_each_source_to_all_destinations(monkeypatch):
    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    client = SimpleNamespace(add_event_handler=Mock(), remove_event_handler=Mock())
    sender = AsyncMock(return_value=SimpleNamespace(id=99))
    monkeypatch.setattr(auto_forward, "send_message", sender)

    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source A", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -1002, "Source B", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -2001, "Destination A", ChannelType.DESTINATION)
        ChannelRepository.upsert(session, -2002, "Destination B", ChannelType.DESTINATION)

    assert await auto_forward.enable(client)
    event = SimpleNamespace(chat_id=-1002, client=client, message=SimpleNamespace(id=7))
    await auto_forward._handler(event)

    assert sender.await_count == 2
    assert {
        call.args[3] for call in sender.await_args_list
    } == {-2001, -2002}
    assert all(call.args[2] == -1002 for call in sender.await_args_list)


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
