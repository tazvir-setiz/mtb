from app.database.database import get_session
from app.database.models import JobStatus, MessageStatus
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
            ForwardJobRepository.increment(
                session,
                job,
                success=int(status == MessageStatus.SUCCESS),
                failed=int(status == MessageStatus.FAILED),
                skipped=int(status in (MessageStatus.SKIPPED, MessageStatus.DUPLICATE)),
                last_message_id=message_id,
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
