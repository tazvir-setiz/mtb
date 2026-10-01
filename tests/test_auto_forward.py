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
from app.services import review_store
from app.services.ai_policy import AIReviewRequired
from app.telegram import auto_forward


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "skip", "failure"])
async def test_live_listener_records_shared_sender_outcome(monkeypatch, outcome):
    prepared = object() if outcome != "skip" else None
    prepare = AsyncMock(return_value=prepared)
    sender = AsyncMock(return_value=SimpleNamespace(id=99))
    if outcome == "failure":
        sender.side_effect = ConnectionError("offline")
    monkeypatch.setattr(auto_forward, "prepare_message", prepare)
    monkeypatch.setattr(auto_forward, "send_prepared_message", sender)

    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, -1, -1, 0).id
        SettingsRepository.set(session, "signature_text", "<b>sig</b>")

    event = SimpleNamespace(client=object(), message=SimpleNamespace(id=7))
    await auto_forward._on_new_message(event, -1001, [(-1002, job_id)])

    prepare.assert_awaited_once_with(event.message, -1001, "<b>sig</b>")
    if outcome != "skip":
        sender.assert_awaited_once_with(
            event.client,
            event.message,
            -1001,
            -1002,
            prepared,
        )

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
        await auto_forward._on_new_message(event, -1001, [(-1002, job_id)])
        assert prepare.await_count == 1
        assert sender.await_count == 1


@pytest.mark.asyncio
async def test_listener_prepares_once_and_fans_out_to_all_destinations(monkeypatch):
    prepared = object()
    prepare = AsyncMock(return_value=prepared)
    sender = AsyncMock(return_value=SimpleNamespace(id=99))
    monkeypatch.setattr(auto_forward, "prepare_message", prepare)
    monkeypatch.setattr(auto_forward, "send_prepared_message", sender)

    with get_session() as session:
        first_job = ForwardJobRepository.create(session, -1001, -2001, -1, -1, 0).id
        second_job = ForwardJobRepository.create(session, -1001, -2002, -1, -1, 0).id
        SettingsRepository.set(session, "signature_text", "<b>sig</b>")

    event = SimpleNamespace(client=object(), message=SimpleNamespace(id=7))
    await auto_forward._on_new_message(
        event,
        -1001,
        [(-2001, first_job), (-2002, second_job)],
    )

    prepare.assert_awaited_once_with(event.message, -1001, "<b>sig</b>")
    assert sender.await_count == 2
    assert {call.args[3] for call in sender.await_args_list} == {-2001, -2002}


@pytest.mark.asyncio
async def test_review_is_created_once_for_all_destinations(monkeypatch):
    prepare = AsyncMock(side_effect=AIReviewRequired("review"))
    monkeypatch.setattr(auto_forward, "prepare_message", prepare)

    with get_session() as session:
        first_job = ForwardJobRepository.create(session, -1001, -2001, -1, -1, 0).id
        second_job = ForwardJobRepository.create(session, -1001, -2002, -1, -1, 0).id

    event = SimpleNamespace(
        client=object(),
        message=SimpleNamespace(
            id=7,
            message="needs review",
            entities=[],
            media=None,
        ),
    )
    await auto_forward._on_new_message(
        event,
        -1001,
        [(-2001, first_job), (-2002, second_job)],
    )

    rows = review_store.pending()
    assert len(rows) == 1
    assert review_store.routes(rows[0]) == [
        (-2001, first_job),
        (-2002, second_job),
    ]
    prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_listener_forwards_each_source_to_all_destinations(monkeypatch):
    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    client = SimpleNamespace(add_event_handler=Mock(), remove_event_handler=Mock())
    prepared = object()
    prepare = AsyncMock(return_value=prepared)
    sender = AsyncMock(return_value=SimpleNamespace(id=99))
    monkeypatch.setattr(auto_forward, "prepare_message", prepare)
    monkeypatch.setattr(auto_forward, "send_prepared_message", sender)

    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source A", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -1002, "Source B", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -2001, "Destination A", ChannelType.DESTINATION)
        ChannelRepository.upsert(session, -2002, "Destination B", ChannelType.DESTINATION)

    assert await auto_forward.enable(client)
    event = SimpleNamespace(
        chat_id=-1002,
        client=client,
        message=SimpleNamespace(id=7),
    )
    await auto_forward._handler(event)

    prepare.assert_awaited_once()
    assert sender.await_count == 2
    assert {call.args[3] for call in sender.await_args_list} == {-2001, -2002}
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
