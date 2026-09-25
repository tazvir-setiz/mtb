from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Channel,
    ChannelType,
    ForwardedMessage,
    ForwardJob,
    JobStatus,
    MessageStatus,
    Settings as SettingsModel,
)


class ChannelRepository:
    @staticmethod
    def upsert(
        session: Session,
        telegram_id: int,
        title: str,
        channel_type: ChannelType,
        username: str | None = None,
    ) -> Channel:
        existing = session.execute(
            select(Channel).where(
                Channel.telegram_id == telegram_id, Channel.type == channel_type
            )
        ).scalar_one_or_none()
        if existing:
            existing.title = title
            existing.username = username
            existing.updated_at = datetime.utcnow()
            session.flush()
            return existing

        # هر نوع کانال (مبدأ/مقصد) فقط یک رکورد فعال دارد؛ رکورد قبلی حذف می‌شود
        old = session.execute(
            select(Channel).where(Channel.type == channel_type)
        ).scalars().all()
        for row in old:
            session.delete(row)
        session.flush()

        channel = Channel(
            telegram_id=telegram_id, title=title, username=username, type=channel_type
        )
        session.add(channel)
        session.flush()
        return channel

    @staticmethod
    def get_by_type(session: Session, channel_type: ChannelType) -> Channel | None:
        return session.execute(
            select(Channel).where(Channel.type == channel_type)
        ).scalar_one_or_none()


class ForwardJobRepository:
    @staticmethod
    def create(
        session: Session,
        source_channel_id: int,
        destination_channel_id: int,
        start_message_id: int,
        end_message_id: int,
        total_messages: int,
    ) -> ForwardJob:
        job = ForwardJob(
            source_channel_id=source_channel_id,
            destination_channel_id=destination_channel_id,
            start_message_id=start_message_id,
            end_message_id=end_message_id,
            total_messages=total_messages,
            status=JobStatus.PENDING,
        )
        session.add(job)
        session.flush()
        return job

    @staticmethod
    def get(session: Session, job_id: int) -> ForwardJob | None:
        return session.get(ForwardJob, job_id)

    @staticmethod
    def get_last_incomplete(session: Session) -> ForwardJob | None:
        return session.execute(
            select(ForwardJob)
            .where(ForwardJob.status.in_([JobStatus.RUNNING, JobStatus.PAUSED]))
            .order_by(ForwardJob.id.desc())
        ).scalars().first()

    @staticmethod
    def update_status(session: Session, job: ForwardJob, status: JobStatus) -> None:
        job.status = status
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = datetime.utcnow()
        if status in (JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED):
            job.finished_at = datetime.utcnow()
        session.flush()

    @staticmethod
    def increment(
        session: Session,
        job: ForwardJob,
        success: int = 0,
        failed: int = 0,
        skipped: int = 0,
        last_message_id: int | None = None,
    ) -> None:
        job.successful_messages += success
        job.failed_messages += failed
        job.skipped_messages += skipped
        if last_message_id is not None:
            job.last_processed_message_id = last_message_id
        session.flush()


class ForwardedMessageRepository:
    @staticmethod
    def exists(
        session: Session, source_channel_id: int, source_message_id: int, destination_channel_id: int
    ) -> ForwardedMessage | None:
        return session.execute(
            select(ForwardedMessage).where(
                ForwardedMessage.source_channel_id == source_channel_id,
                ForwardedMessage.source_message_id == source_message_id,
                ForwardedMessage.destination_channel_id == destination_channel_id,
                ForwardedMessage.status == MessageStatus.SUCCESS,
            )
        ).scalar_one_or_none()

    @staticmethod
    def record(
        session: Session,
        job_id: int,
        source_channel_id: int,
        source_message_id: int,
        destination_channel_id: int,
        status: MessageStatus,
        destination_message_id: int | None = None,
        error: str | None = None,
    ) -> ForwardedMessage:
        record = session.execute(
            select(ForwardedMessage).where(
                ForwardedMessage.source_channel_id == source_channel_id,
                ForwardedMessage.source_message_id == source_message_id,
                ForwardedMessage.destination_channel_id == destination_channel_id,
            )
        ).scalar_one_or_none()
        if record:
            record.status = status
            record.destination_message_id = destination_message_id
            record.error = error
            record.job_id = job_id
        else:
            record = ForwardedMessage(
                job_id=job_id,
                source_channel_id=source_channel_id,
                source_message_id=source_message_id,
                destination_channel_id=destination_channel_id,
                destination_message_id=destination_message_id,
                status=status,
                error=error,
            )
            session.add(record)
        session.flush()
        return record

    @staticmethod
    def failed_for_job(session: Session, job_id: int) -> list[ForwardedMessage]:
        return list(
            session.execute(
                select(ForwardedMessage).where(
                    ForwardedMessage.job_id == job_id,
                    ForwardedMessage.status == MessageStatus.FAILED,
                )
            ).scalars()
        )

    @staticmethod
    def recent(session: Session, limit: int = 10) -> list[ForwardedMessage]:
        return list(
            session.execute(
                select(ForwardedMessage).order_by(ForwardedMessage.id.desc()).limit(limit)
            ).scalars()
        )

    @staticmethod
    def stats(session: Session) -> dict:
        rows = list(session.execute(select(ForwardedMessage)).scalars())
        total = len(rows)
        success = sum(1 for r in rows if r.status == MessageStatus.SUCCESS)
        failed = sum(1 for r in rows if r.status == MessageStatus.FAILED)
        duplicate = sum(1 for r in rows if r.status == MessageStatus.DUPLICATE)
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "duplicate": duplicate,
        }


class SettingsRepository:
    @staticmethod
    def get(session: Session, key: str, default: str | None = None) -> str | None:
        row = session.execute(
            select(SettingsModel).where(SettingsModel.key == key)
        ).scalar_one_or_none()
        return row.value if row else default

    @staticmethod
    def set(session: Session, key: str, value: str) -> None:
        row = session.execute(
            select(SettingsModel).where(SettingsModel.key == key)
        ).scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(SettingsModel(key=key, value=value))
        session.flush()

    @staticmethod
    def clear_all_data(session: Session) -> None:
        session.query(ForwardedMessage).delete()
        session.query(ForwardJob).delete()
        session.flush()
