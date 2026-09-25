from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ForwardJob, JobStatus


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
        return (
            session.execute(
                select(ForwardJob)
                .where(ForwardJob.status.in_([JobStatus.RUNNING, JobStatus.PAUSED]))
                .order_by(ForwardJob.id.desc())
            )
            .scalars()
            .first()
        )

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
