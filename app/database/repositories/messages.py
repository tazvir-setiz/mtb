from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ForwardedMessage, MessageStatus


class ForwardedMessageRepository:
    @staticmethod
    def exists(
        session: Session,
        source_channel_id: int,
        source_message_id: int,
        destination_channel_id: int,
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
