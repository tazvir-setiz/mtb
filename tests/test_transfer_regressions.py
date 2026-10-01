import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_forward_service import FakeClient

from app.database.database import get_session
from app.database.models import JobMessageResult, JobStatus, MessageStatus
from app.database.repository import (
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.handlers import transfer_controls
from app.handlers.states import KEY_CURRENT_JOB_ID
from app.services import ai_service, transfer_service
from app.telegram import auto_forward, forward_service


@pytest.mark.asyncio
async def test_three_transfers_send_only_once():
    client = FakeClient()
    for _ in range(3):
        with get_session() as session:
            job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 1, 1).id
        await forward_service.forward_range(client, job_id, -1001, -1002, [1])
    assert client.calls == [1]
    with get_session() as session:
        sent = ForwardedMessageRepository.exists(session, -1001, 1, -1002)
        assert sent.destination_message_id == 10001


@pytest.mark.asyncio
async def test_successful_retry_replaces_failure_count():
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 1, 1).id
    client = FakeClient(fail_ids={1})
    await forward_service.forward_range(client, job_id, -1001, -1002, [1])
    await forward_service.retry_failed(client, job_id)
    client.fail_ids.clear()
    await forward_service.retry_failed(client, job_id)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert (job.total_messages, job.successful_messages, job.failed_messages) == (1, 1, 0)


@pytest.mark.asyncio
async def test_resume_preserves_explicit_selection(monkeypatch):
    job_id = transfer_service.create_job_for_ids(-1001, -1002, [1, 10])
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        job.last_processed_message_id = 1
        job.status = JobStatus.PAUSED
    captured = AsyncMock()
    monkeypatch.setattr(transfer_service, "run_transfer", captured)
    tasks = []
    monkeypatch.setattr(transfer_controls.asyncio, "create_task", tasks.append)
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(message_id=1)),
        effective_chat=SimpleNamespace(id=111),
    )
    await transfer_controls.resume_transfer(
        update, SimpleNamespace(user_data={KEY_CURRENT_JOB_ID: job_id})
    )
    await tasks[0]
    assert captured.call_args.args[-1] == [10]


@pytest.mark.asyncio
async def test_progress_failure_does_not_abort_transfer():
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 2, 2).id
    client = FakeClient()
    await forward_service.forward_range(
        client,
        job_id,
        -1001,
        -1002,
        [1, 2],
        AsyncMock(side_effect=RuntimeError("status UI unavailable")),
    )
    assert client.calls == [1, 2]
    with get_session() as session:
        assert ForwardJobRepository.get(session, job_id).status == JobStatus.COMPLETED


@pytest.mark.asyncio
@pytest.mark.parametrize("auto_first", [True, False])
async def test_auto_and_manual_send_same_message_only_once(monkeypatch, auto_first):
    entered = asyncio.Event()
    release = asyncio.Event()
    sent = []

    async def send(*args):
        sent.append(1)
        entered.set()
        await release.wait()
        return SimpleNamespace(id=100)

    monkeypatch.setattr(auto_forward, "send_prepared_message", send)
    monkeypatch.setattr(forward_service, "send_prepared_message", send)
    with get_session() as session:
        a = ForwardJobRepository.create(session, -1001, -1002, 1, 1, 1).id
        b = ForwardJobRepository.create(session, -1001, -1002, 1, 1, 1).id
    client = FakeClient()
    event = SimpleNamespace(
        client=client, message=SimpleNamespace(id=1, message="1", entities=[], media=None)
    )
    operations = [
        auto_forward._on_new_message(event, -1001, [(-1002, a)]),
        forward_service.forward_range(client, b, -1001, -1002, [1]),
    ]
    if not auto_first:
        operations.reverse()
    first = asyncio.create_task(operations[0])
    await entered.wait()
    second = asyncio.create_task(operations[1])
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert sent == [1]


def test_long_custom_guard_is_preserved(monkeypatch):
    custom = "قانون سفارشی. " * 100
    monkeypatch.setattr(ai_service, "settings", replace(ai_service.settings, ai_guardrails=custom))
    assert custom.strip() in ai_service.compact_prompt()


def test_legacy_sparse_job_cannot_resume_as_range():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 1, 10, 2)
        with pytest.raises(ValueError, match="فهرست"):
            transfer_service.remaining_ids(session, job)


def test_legacy_contiguous_job_can_resume():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 1, 10, 10)
        job.last_processed_message_id = 8
        assert transfer_service.remaining_ids(session, job) == [9, 10]


@pytest.mark.asyncio
async def test_rerunning_same_job_keeps_counts_and_sent_id():
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 1, 1).id
    client = FakeClient()
    for _ in range(3):
        await forward_service.forward_range(client, job_id, -1001, -1002, [1])
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert (job.successful_messages, job.skipped_messages, job.failed_messages) == (1, 0, 0)
        assert (
            ForwardedMessageRepository.exists(session, -1001, 1, -1002).destination_message_id
            == 10001
        )


def test_clearing_history_removes_new_job_metadata():
    from app.services.forward_results import record_result

    job_id = transfer_service.create_job_for_ids(-1001, -1002, [1, 10])
    record_result(job_id, -1001, 1, -1002, MessageStatus.FAILED)
    with get_session() as session:
        SettingsRepository.clear_all_data(session)
    with get_session() as session:
        assert session.get(JobMessageResult, (job_id, 1)) is None
        assert SettingsRepository.get(session, f"job_selection:{job_id}") is None


def test_resolving_old_review_does_not_move_resume_cursor_back():
    from app.services.forward_results import record_result
    from app.services.review_service import record_resolution

    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 10, 10).id
    record_result(job_id, -1001, 1, -1002, MessageStatus.FAILED)
    record_result(job_id, -1001, 10, -1002, MessageStatus.SUCCESS, destination_message_id=10010)
    row = SimpleNamespace(job_id=job_id, source_id=-1001, destination_id=-1002, message_id=1)
    record_resolution(row, MessageStatus.SUCCESS, 10001)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert job.last_processed_message_id == 10
        assert (job.successful_messages, job.failed_messages) == (2, 0)
