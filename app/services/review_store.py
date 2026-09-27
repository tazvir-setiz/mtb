import hashlib
import json
import logging

from sqlalchemy import select, update
from telethon.extensions import html

from app.database.database import get_session
from app.database.models import ReviewDraft, ReviewRequest

logger = logging.getLogger(__name__)


def content_fingerprint(message):
    def stable(value):
        if isinstance(value, dict):
            return {
                k: stable(v)
                for k, v in value.items()
                if k not in {"file_reference", "access_hash", "results"}
            }
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value

    media = getattr(message, "media", None)
    data = (
        html.unparse(message.message or "", message.entities or []),
        stable(media.to_dict()) if media else None,
    )
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def find(source_id, message_id, destination_id):
    with get_session() as session:
        return session.scalar(
            select(ReviewRequest).where(
                ReviewRequest.source_id == source_id,
                ReviewRequest.message_id == message_id,
                ReviewRequest.destination_id == destination_id,
            )
        )


def enqueue(original, source_id, destination_id, job_id, reason):
    with get_session() as session:
        row = session.scalar(
            select(ReviewRequest).where(
                ReviewRequest.source_id == source_id,
                ReviewRequest.message_id == original.id,
                ReviewRequest.destination_id == destination_id,
            )
        )
        fingerprint = content_fingerprint(original)
        if row is None:
            row = ReviewRequest(
                source_id=source_id, message_id=original.id, destination_id=destination_id
            )
            session.add(row)
        elif row.fingerprint == fingerprint or row.status in {"sending", "sent"}:
            return row
        row.job_id = job_id
        if row.id is not None:
            draft = session.get(ReviewDraft, row.id)
            if draft:
                session.delete(draft)
        row.fingerprint = fingerprint
        row.preview = (original.message or "[پیام رسانه‌ای یا نظرسنجی بدون متن]")[:2500]
        row.reason = reason[:100]
        row.status = "pending"
        row.notified = "[]"
        session.flush()
        logger.info(
            "Review queued review_id=%d source=%s message=%s destination=%s reason=%s",
            row.id,
            source_id,
            original.id,
            destination_id,
            row.reason,
        )
        return row


def get(review_id):
    with get_session() as session:
        return session.get(ReviewRequest, review_id)


def pending(limit=20, after_id=0):
    with get_session() as session:
        return list(
            session.scalars(
                select(ReviewRequest)
                .where(
                    ReviewRequest.status.in_(["pending", "sending", "uncertain"]),
                    ReviewRequest.id > after_id,
                )
                .order_by(ReviewRequest.id)
                .limit(limit)
            )
        )


def claim(review_id, admin_id):
    with get_session() as session:
        return (
            session.execute(
                update(ReviewRequest)
                .where(ReviewRequest.id == review_id, ReviewRequest.status == "pending")
                .values(status="sending", decided_by=admin_id)
            ).rowcount
            == 1
        )


def set_status(review_id, status, destination_message_id=None):
    with get_session() as session:
        row = session.get(ReviewRequest, review_id)
        row.status = status
        row.destination_message_id = destination_message_id


def mark_notified(review_id, admin_id, fingerprint=None, status=None, version=None):
    from app.services import review_drafts

    with get_session() as session:
        row = session.get(ReviewRequest, review_id)
        if (
            not row
            or (fingerprint and row.fingerprint != fingerprint)
            or (status and row.status != status)
            or (version and review_drafts.version(row) != version)
        ):
            return
        row.notified = json.dumps(sorted(set(json.loads(row.notified)) | {admin_id}))


def recover_interrupted():
    with get_session() as session:
        session.execute(
            update(ReviewRequest)
            .where(ReviewRequest.status == "sending")
            .values(status="uncertain", notified="[]")
        )


def requeue(review_id, reason):
    with get_session() as session:
        row = session.get(ReviewRequest, review_id)
        row.status = "pending"
        row.reason = reason
        row.notified = "[]"


def reopen_uncertain(review_id, admin_id):
    with get_session() as session:
        return (
            session.execute(
                update(ReviewRequest)
                .where(ReviewRequest.id == review_id, ReviewRequest.status == "uncertain")
                .values(status="pending", notified="[]", decided_by=admin_id)
            ).rowcount
            == 1
        )
