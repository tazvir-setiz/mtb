from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.errors import ChatAdminRequiredError, FloodWaitError

from app.database.database import get_session
from app.database.models import JobStatus, MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository
from app.telegram import forward_service
from app.telegram.forward_service import (
    ForwardErrorType,
    classify_error,
    forward_range,
)


class FakeMessage:
    def __init__(self, msg_id: int):
        self.id = msg_id


class FakeClient:
    """کلاینت جعلی Telethon برای تست بدون نیاز به اتصال واقعی."""

    def __init__(self, fail_ids: set[int] | None = None):
        self.fail_ids = fail_ids or set()
        self.calls: list[int] = []

    async def get_messages(self, entity, ids):
        return [SimpleNamespace(id=ids[0], message=str(ids[0]), entities=[], media=None)]

    async def send_message(self, entity, message, **kwargs):
        msg_id = int(message)
        self.calls.append(msg_id)
        if msg_id in self.fail_ids:
            raise ChatAdminRequiredError(request=SimpleNamespace())
        return FakeMessage(msg_id + 10000)


def test_classify_error_admin_required():
    exc = ChatAdminRequiredError(request=SimpleNamespace())
    assert classify_error(exc) == ForwardErrorType.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_forward_range_success_and_duplicate():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 1, 3, 3)
        job_id = job.id

    client = FakeClient()
    await forward_range(client, job_id, -1001, -1002, [1, 2, 3])

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert job.status == JobStatus.COMPLETED
        assert job.successful_messages == 3
        assert job.failed_messages == 0

    # اجرای دوباره باید همه را به‌عنوان تکراری تشخیص دهد
    with get_session() as session:
        job2 = ForwardJobRepository.create(session, -1001, -1002, 1, 3, 3)
        job2_id = job2.id
    await forward_range(client, job2_id, -1001, -1002, [1, 2, 3])
    with get_session() as session:
        job2 = ForwardJobRepository.get(session, job2_id)
        assert job2.skipped_messages == 3


@pytest.mark.asyncio
async def test_forward_range_records_failure():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1003, 10, 10, 1)
        job_id = job.id

    client = FakeClient(fail_ids={10})
    await forward_range(client, job_id, -1001, -1003, [10])

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert job.failed_messages == 1
        failed = ForwardedMessageRepository.failed_for_job(session, job_id)
        assert len(failed) == 1
        assert failed[0].status == MessageStatus.FAILED
        assert failed[0].error == "⚠️ دسترسی کافی نیست"


@pytest.mark.asyncio
@pytest.mark.parametrize("result_kind", ["success", "skip", "failure"])
async def test_flood_wait_retries_once_and_records_result(monkeypatch, result_kind):
    result = {
        "success": FakeMessage(999),
        "skip": None,
        "failure": ChatAdminRequiredError(request=None),
    }[result_kind]
    sender = AsyncMock(side_effect=[FloodWaitError(request=None, capture=2), result])
    monkeypatch.setattr(forward_service, "fetch_and_send_message", sender)
    sleep = AsyncMock()
    monkeypatch.setattr(forward_service.asyncio, "sleep", sleep)
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 7, 7, 1).id

    snapshots = []

    async def progress(snapshot):
        snapshots.append(snapshot)

    await forward_range(FakeClient(), job_id, -1001, -1002, [7], progress)
    assert sender.await_count == 2
    assert sleep.call_args_list[0].args == (3,)
    assert snapshots[0].processed == 0
    assert snapshots[-1].processed == 1
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert job.status == JobStatus.COMPLETED
        assert job.successful_messages == int(result_kind == "success")
        assert job.skipped_messages == int(result_kind == "skip")
        assert job.failed_messages == int(result_kind == "failure")
        record = ForwardedMessageRepository.recent(session)[0]
        if result_kind == "success":
            assert record.destination_message_id == 999
        elif result_kind == "skip":
            assert record.status == MessageStatus.SKIPPED
        else:
            assert record.error == "⚠️ دسترسی کافی نیست"


@pytest.mark.asyncio
async def test_pause_stops_before_next_message():
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 3, 3).id
    snapshots = []

    async def progress(snapshot):
        snapshots.append(snapshot)
        if not snapshot.stopped:
            forward_service.request_stop(job_id)

    client = FakeClient()
    await forward_range(client, job_id, -1001, -1002, [1, 2, 3], progress)
    assert client.calls == [1]
    assert snapshots[-1].stopped
    with get_session() as session:
        assert ForwardJobRepository.get(session, job_id).status == JobStatus.PAUSED


@pytest.mark.asyncio
async def test_retry_only_failed_messages():
    with get_session() as session:
        job_id = ForwardJobRepository.create(session, -1001, -1002, 1, 2, 2).id
    await forward_range(FakeClient(fail_ids={2}), job_id, -1001, -1002, [1, 2])
    client = FakeClient()
    await forward_service.retry_failed(client, job_id)
    assert client.calls == [2]
    with get_session() as session:
        assert ForwardedMessageRepository.failed_for_job(session, job_id) == []
