from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.database.database import get_session
from app.database.models import (
    Channel,
    ChannelType,
    ForwardedMessage,
    ForwardJob,
    JobMessageResult,
    JobStatus,
    MessageStatus,
    ReviewDraft,
    ReviewRequest,
    Settings as SettingsModel,
)
from app.database.repository import ChannelRepository, SettingsRepository
from app.services.cleanup_service import (
    auto_cleanup_loop,
    cleanup_old_data,
    run_database_cleanup,
    vacuum_database,
)
from app.services.statistics_service import get_system_health_report


def test_cleanup_old_data_purges_past_records_and_preserves_recent():
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=15)
    recent_time = now - timedelta(days=2)

    with get_session() as session:
        # Channels must never be deleted
        ChannelRepository.upsert(session, -100111, "Test Source", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -100222, "Test Dest", ChannelType.DESTINATION)

        # Core settings must never be deleted
        SettingsRepository.set(session, "signature_text", "My Custom Signature")

        # Stale temporary settings (should be deleted)
        session.add(SettingsModel(key="job_selection:123", value="temp"))
        session.add(SettingsModel(key="route_sending:-1001", value="temp2"))

        # Old job (15 days ago)
        old_job = ForwardJob(
            source_channel_id=-100111,
            destination_channel_id=-100222,
            start_message_id=1,
            end_message_id=10,
            status=JobStatus.COMPLETED,
            created_at=old_time,
        )
        session.add(old_job)
        session.flush()

        old_msg = ForwardedMessage(
            job_id=old_job.id,
            source_channel_id=-100111,
            source_message_id=5,
            destination_channel_id=-100222,
            destination_message_id=50,
            status=MessageStatus.SUCCESS,
            created_at=old_time,
        )
        session.add(old_msg)
        session.add(JobMessageResult(job_id=old_job.id, message_id=5, status=MessageStatus.SUCCESS))

        # Recent job (2 days ago)
        recent_job = ForwardJob(
            source_channel_id=-100111,
            destination_channel_id=-100222,
            start_message_id=20,
            end_message_id=30,
            status=JobStatus.COMPLETED,
            created_at=recent_time,
        )
        session.add(recent_job)
        session.flush()

        recent_msg = ForwardedMessage(
            job_id=recent_job.id,
            source_channel_id=-100111,
            source_message_id=25,
            destination_channel_id=-100222,
            destination_message_id=60,
            status=MessageStatus.SUCCESS,
            created_at=recent_time,
        )
        session.add(recent_msg)
        session.add(JobMessageResult(job_id=recent_job.id, message_id=25, status=MessageStatus.SUCCESS))

        # Old review request (15 days ago)
        old_review = ReviewRequest(
            source_id=-100111,
            message_id=88,
            destination_id=-100222,
            fingerprint="old_fp",
            preview="Old text",
            reason="abuse",
            created_at=old_time,
        )
        session.add(old_review)
        session.flush()
        session.add(ReviewDraft(review_id=old_review.id, text="Draft text", revision="rev1"))

        # Recent review request (2 days ago)
        recent_review = ReviewRequest(
            source_id=-100111,
            message_id=99,
            destination_id=-100222,
            fingerprint="recent_fp",
            preview="Recent text",
            reason="rewrite",
            created_at=recent_time,
        )
        session.add(recent_review)
        session.flush()
        session.add(ReviewDraft(review_id=recent_review.id, text="Recent draft", revision="rev2"))

    # Execute cleanup with 7 days retention
    with get_session() as session:
        stats = cleanup_old_data(session, retention_days=7)
        assert stats["reviews"] >= 1
        assert stats["drafts"] >= 1
        assert stats["jobs"] >= 1
        assert stats["forwarded_messages"] >= 1
        assert stats["temp_settings"] >= 2

    # Verify state after cleanup
    with get_session() as session:
        # Channels still exist
        assert ChannelRepository.get_by_type(session, ChannelType.SOURCE) is not None
        assert ChannelRepository.get_by_type(session, ChannelType.DESTINATION) is not None

        # Core setting still exists
        assert SettingsRepository.get(session, "signature_text") == "My Custom Signature"

        # Stale settings are gone
        assert session.execute(
            select(SettingsModel).where(SettingsModel.key.startswith("job_selection:"))
        ).scalar_one_or_none() is None

        # Old job and old messages are gone
        assert session.get(ForwardJob, old_job.id) is None
        assert session.execute(
            select(ForwardedMessage).where(ForwardedMessage.source_message_id == 5)
        ).scalar_one_or_none() is None

        # Recent job and recent messages are preserved!
        assert session.get(ForwardJob, recent_job.id) is not None
        assert session.execute(
            select(ForwardedMessage).where(ForwardedMessage.source_message_id == 25)
        ).scalar_one_or_none() is not None

        # Old review is gone, recent review is preserved!
        assert session.get(ReviewRequest, old_review.id) is None
        assert session.get(ReviewRequest, recent_review.id) is not None


def test_vacuum_database_executes_cleanly():
    result = vacuum_database()
    assert result is True


def test_run_database_cleanup_wrapper():
    stats = run_database_cleanup(retention_days=7)
    assert isinstance(stats, dict)
    assert "vacuum" in stats
    assert stats["vacuum"] is True


@pytest.mark.asyncio
async def test_auto_cleanup_loop_runs_and_cancels():
    task = asyncio.create_task(
        auto_cleanup_loop(interval_hours=0.0001, retention_days=7, initial_delay_seconds=0.01)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_health_report_includes_auto_cleanup_status():
    report = await get_system_health_report()
    assert "پاک‌سازی خودکار" in report
    assert "فعال" in report
