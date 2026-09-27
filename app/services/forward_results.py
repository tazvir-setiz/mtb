from sqlalchemy import select

from app.database.database import get_session
from app.database.models import ForwardedMessage, JobMessageResult, JobStatus, MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository


def set_job_status(job_id: int, status: JobStatus) -> None:
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job:
            ForwardJobRepository.update_status(session, job, status)


def record_result(
    job_id: int,
    source_id: int,
    message_id: int,
    destination_id: int,
    status: MessageStatus,
    *,
    destination_message_id: int | None = None,
    error: str | None = None,
) -> None:
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job:
            result = session.get(JobMessageResult, (job_id, message_id))
            previous = (
                result.status
                if result
                else session.scalar(
                    select(ForwardedMessage.status).where(
                        ForwardedMessage.job_id == job_id,
                        ForwardedMessage.source_message_id == message_id,
                        ForwardedMessage.source_channel_id == source_id,
                        ForwardedMessage.destination_channel_id == destination_id,
                    )
                )
            )
            if previous == MessageStatus.SUCCESS and status == MessageStatus.DUPLICATE:
                status = previous
            for field, statuses in (
                ("successful_messages", {MessageStatus.SUCCESS}),
                ("failed_messages", {MessageStatus.FAILED}),
                ("skipped_messages", {MessageStatus.SKIPPED, MessageStatus.DUPLICATE}),
            ):
                if previous in statuses:
                    setattr(job, field, max(0, getattr(job, field) - 1))
            if result:
                result.status = status
            else:
                session.add(JobMessageResult(job_id=job_id, message_id=message_id, status=status))
            ForwardJobRepository.increment(
                session,
                job,
                success=int(status == MessageStatus.SUCCESS),
                failed=int(status == MessageStatus.FAILED),
                skipped=int(status in (MessageStatus.SKIPPED, MessageStatus.DUPLICATE)),
                last_message_id=max(job.last_processed_message_id or 0, message_id),
            )
        ForwardedMessageRepository.record(
            session,
            job_id,
            source_id,
            message_id,
            destination_id,
            status,
            destination_message_id=destination_message_id,
            error=error,
        )
