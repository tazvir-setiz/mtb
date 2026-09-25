from app.database.database import get_session
from app.database.models import ChannelType, JobStatus, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
)


def test_channel_upsert_and_get():
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "Source Ch", ChannelType.SOURCE, "source_ch")
    with get_session() as session:
        channel = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        assert channel is not None
        assert channel.title == "Source Ch"
        assert channel.username == "source_ch"


def test_channel_upsert_replaces_previous_of_same_type():
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "First", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -1002, "Second", ChannelType.SOURCE)
    with get_session() as session:
        channel = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        assert channel.telegram_id == -1002
        assert channel.title == "Second"


def test_job_creation_and_status_update():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 100, 150, 51)
        job_id = job.id
        assert job.status == JobStatus.PENDING

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)
        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None


def test_duplicate_detection():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 100, 100, 1)
        job_id = job.id
        ForwardedMessageRepository.record(
            session, job_id, -1001, 100, -1002, MessageStatus.SUCCESS, destination_message_id=5
        )

    with get_session() as session:
        found = ForwardedMessageRepository.exists(session, -1001, 100, -1002)
        assert found is not None

        not_found = ForwardedMessageRepository.exists(session, -1001, 999, -1002)
        assert not_found is None


def test_retry_failed_messages_query():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 100, 101, 2)
        job_id = job.id
        ForwardedMessageRepository.record(
            session, job_id, -1001, 100, -1002, MessageStatus.SUCCESS
        )
        ForwardedMessageRepository.record(
            session, job_id, -1001, 101, -1002, MessageStatus.FAILED, error="⚠️ خطا"
        )

    with get_session() as session:
        failed = ForwardedMessageRepository.failed_for_job(session, job_id)
        assert len(failed) == 1
        assert failed[0].source_message_id == 101


def test_statistics_counts():
    with get_session() as session:
        job = ForwardJobRepository.create(session, -1001, -1002, 1, 3, 3)
        job_id = job.id
        ForwardedMessageRepository.record(session, job_id, -1001, 1, -1002, MessageStatus.SUCCESS)
        ForwardedMessageRepository.record(session, job_id, -1001, 2, -1002, MessageStatus.FAILED)
        ForwardedMessageRepository.record(session, job_id, -1001, 3, -1002, MessageStatus.DUPLICATE)

    with get_session() as session:
        stats = ForwardedMessageRepository.stats(session)
        assert stats["total"] == 3
        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["duplicate"] == 1
