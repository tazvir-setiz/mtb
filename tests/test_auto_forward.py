from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.database import get_session
from app.database.models import MessageStatus
from app.database.repository import (
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
