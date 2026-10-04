from __future__ import annotations

from sqlalchemy import func, select
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
            if record.status == MessageStatus.SUCCESS:
                return record
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
        counts = session.execute(
            select(ForwardedMessage.status, func.count(ForwardedMessage.id)).group_by(
                ForwardedMessage.status
            )
        ).all()
        status_counts = dict(counts)
        total = sum(status_counts.values())
        return {
            "total": total,
            "success": status_counts.get(MessageStatus.SUCCESS, 0),
            "failed": status_counts.get(MessageStatus.FAILED, 0),
            "duplicate": status_counts.get(MessageStatus.DUPLICATE, 0),
        }
