import asyncio
from types import SimpleNamespace

import pytest

from app.database.database import get_session
from app.database.models import JobStatus, MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository
from app.telegram.forward_service import (
    ForwardErrorType,
    classify_error,
    forward_range,
)
from telethon.errors import ChatAdminRequiredError


class FakeMessage:
    def __init__(self, msg_id: int):
        self.id = msg_id


class FakeClient:
    """کلاینت جعلی Telethon برای تست بدون نیاز به اتصال واقعی."""

    def __init__(self, fail_ids: set[int] | None = None):
        self.fail_ids = fail_ids or set()
        self.calls: list[int] = []

    async def forward_messages(self, entity, messages, from_peer):
        self.calls.append(messages)
        if messages in self.fail_ids:
            raise ChatAdminRequiredError(request=SimpleNamespace())
        return FakeMessage(messages + 10000)


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
