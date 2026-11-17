import hashlib
import json
import logging

from sqlalchemy import select, update
from telethon.extensions import html

from app.database.database import get_session
from app.database.models import ReviewDraft, ReviewRequest, Settings
from app.services.review_kind import preserve_review_kind

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
    if media is None:
        for attr in ("photo", "video", "document", "audio", "voice", "animation", "poll"):
            val = getattr(message, attr, None)
            if val:
                media = val
                break

    if hasattr(message, "text_html") and message.text_html:
        msg_text = message.text_html
    elif hasattr(message, "caption_html") and message.caption_html:
        msg_text = message.caption_html
    elif hasattr(message, "message") and message.message is not None:
        msg_text = html.unparse(message.message or "", getattr(message, "entities", None) or [])
    else:
        msg_text = getattr(message, "text", "") or getattr(message, "caption", "") or ""

    media_dict = None
    if media:
        if hasattr(media, "to_dict"):
            media_dict = stable(media.to_dict())
        elif isinstance(media, list) and media and hasattr(media[-1], "file_unique_id"):
            media_dict = {"file_unique_id": media[-1].file_unique_id}
        elif hasattr(media, "file_unique_id"):
            media_dict = {"file_unique_id": media.file_unique_id}
        else:
            media_dict = {"repr": str(media)}

    data = (
        msg_text,
        media_dict,
    )
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _route_key(review_id):
    return f"review_routes:{review_id}"


def _save_routes(session, review_id, routes):
    key = _route_key(review_id)
    value = json.dumps(
        [
            {
                "destination_id": int(destination_id),
                "job_id": int(job_id) if job_id is not None else None,
            }
            for destination_id, job_id in routes
        ]
    )
    row = session.scalar(select(Settings).where(Settings.key == key))
    if row is None:
        session.add(Settings(key=key, value=value))
    else:
        row.value = value


def _load_routes(session, row):
    fallback = [(row.destination_id, row.job_id)]
    if getattr(row, "id", None) is None:
        return fallback
    setting = session.scalar(select(Settings).where(Settings.key == _route_key(row.id)))
    if not setting:
        return fallback
    try:
        data = json.loads(setting.value)
        if not isinstance(data, list) or not data:
            raise ValueError("empty or invalid route list")
        result = {}
        for item in data:
            destination = item["destination_id"]
            job = item.get("job_id")
            if type(destination) is not int or (job is not None and type(job) is not int):
                raise ValueError("invalid route identity")
            result.setdefault(destination, job)
        return list(result.items())
    except (ValueError, TypeError, KeyError):
        logger.warning("Invalid review route metadata review_id=%s; using legacy route", row.id)
        return fallback


def routes(row):
    with get_session() as session:
        return _load_routes(session, row)


def find(source_id, message_id, destination_id):
    with get_session() as session:
        rows = session.scalars(
            select(ReviewRequest)
            .where(
                ReviewRequest.source_id == source_id,
                ReviewRequest.message_id == message_id,
            )
            .order_by(ReviewRequest.id.desc())
        ).all()
        return next(
            (row for row in rows if destination_id in dict(_load_routes(session, row))), None
        )


def find_for_message(source_id, message_id):
    with get_session() as session:
        return session.scalar(
            select(ReviewRequest)
            .where(
                ReviewRequest.source_id == source_id,
                ReviewRequest.message_id == message_id,
            )
            .order_by(ReviewRequest.id.desc())
        )


def enqueue_routes(original, source_id, routes_list, reason):
    if not routes_list:
        return None
    primary_destination, primary_job = routes_list[0]
    orig_id = getattr(original, "id", None) or getattr(original, "message_id", None)
    orig_text = (
        getattr(original, "message", None)
        or getattr(original, "text", None)
        or getattr(original, "caption", None)
    )
    with get_session() as session:
        row = session.scalar(
            select(ReviewRequest).where(
                ReviewRequest.source_id == source_id,
                ReviewRequest.message_id == orig_id,
            )
        )
        fingerprint = content_fingerprint(original)
        if row is None:
            row = ReviewRequest(
                source_id=source_id,
                message_id=orig_id,
                destination_id=primary_destination,
                fingerprint=fingerprint,
                preview=(orig_text or "[پیام بدون متن]")[:2500],
                reason=reason[:100],
            )
            session.add(row)
            session.flush()
        else:
            merged = dict(_load_routes(session, row))
            new_destinations = set(dict(routes_list)) - set(merged)
            for destination, job in routes_list:
                if destination not in merged or merged[destination] is None:
                    merged[destination] = job
            routes_list = list(merged.items())
            if row.status == "rejected":
                # A final rejection applies to the source message identity even if it is edited later.
                _save_routes(session, row.id, routes_list)
                return row
            if row.fingerprint == fingerprint or row.status in {"sending", "sent", "uncertain"}:
                _save_routes(session, row.id, routes_list)
                if new_destinations:
                    row.notified = "[]"
                    if row.status == "sent":
                        row.status = "pending"
                return row

        row.job_id = primary_job
        draft = session.get(ReviewDraft, row.id)
        if draft:
            session.delete(draft)
        row.fingerprint = fingerprint
        row.preview = (orig_text or "[پیام رسانه‌ای یا نظرسنجی بدون متن]")[:2500]
        row.reason = reason[:100]
        row.status = "pending"
        row.notified = "[]"
        _save_routes(session, row.id, routes_list)
        session.flush()
        logger.info(
            "Review queued review_id=%d source=%s message=%s destinations=%d reason=%s",
            row.id,
            source_id,
            orig_id,
            len(routes_list),
            row.reason,
        )
        return row


def enqueue(original, source_id, destination_id, job_id, reason):
    return enqueue_routes(original, source_id, [(destination_id, job_id)], reason)


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
                .where(
                    ReviewRequest.id == review_id,
                    ReviewRequest.status == "pending",
                )
                .values(status="sending", decided_by=admin_id)
            ).rowcount
            == 1
        )


def set_status(review_id, status, destination_message_id=None):
    with get_session() as session:
        row = session.get(ReviewRequest, review_id)
        row.status = status
        row.destination_message_id = destination_message_id
        if status in {"sent", "rejected"}:
            key = _route_key(review_id)
            setting = session.scalar(select(Settings).where(Settings.key == key))
            if setting is not None:
                session.delete(setting)


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
        row.reason = preserve_review_kind(row.reason, reason)
        row.notified = "[]"


def reopen_uncertain(review_id, admin_id):
    with get_session() as session:
        return (
            session.execute(
                update(ReviewRequest)
                .where(
                    ReviewRequest.id == review_id,
                    ReviewRequest.status == "uncertain",
                )
                .values(status="pending", notified="[]", decided_by=admin_id)
            ).rowcount
            == 1
        )
