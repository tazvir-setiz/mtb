"""Shared, serialized prepare-once fan-out for automatic and historical messages."""

import logging

from app.database.database import get_session
from app.database.models import MessageStatus, Settings
from app.database.repository import (
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.services import review_store
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.forward_results import record_result
from app.services.message_locks import message_lock
from app.telegram.forward_errors import FRIENDLY_ERRORS, ForwardErrorType, classify_error

logger = logging.getLogger(__name__)


def delivery_key(source, message, destination):
    return f"route_sending:{source}:{message}:{destination}"


def clear_delivery_marker(source, message, destination):
    with get_session() as session:
        session.query(Settings).filter_by(key=delivery_key(source, message, destination)).delete()


class UncertainDelivery(Exception):
    """A prior send may have reached Telegram; only an admin may authorize retry."""


async def deliver(client, original, source, destination, job, prepared, sender):
    async with message_lock(source, original.id, destination):
        if job is None:
            with get_session() as session:
                job = ForwardJobRepository.create(
                    session, source, destination, original.id, original.id, 1
                ).id
        with get_session() as session:
            already = ForwardedMessageRepository.exists(session, source, original.id, destination)
        if already:
            record_result(job, source, original.id, destination, MessageStatus.DUPLICATE)
            return MessageStatus.DUPLICATE, already.destination_message_id
        with get_session() as session:
            key = delivery_key(source, original.id, destination)
            if SettingsRepository.get(session, key):
                raise UncertainDelivery()
            SettingsRepository.set(session, key, "1")
        try:
            sent = await sender(client, original, source, destination, prepared)
            if sent is None:
                raise UncertainDelivery("Telegram returned no delivery result")
            sent_id = getattr(sent, "id", None)
            record_result(
                job,
                source,
                original.id,
                destination,
                MessageStatus.SUCCESS,
                destination_message_id=sent_id,
            )
            clear_delivery_marker(source, original.id, destination)
            logger.info(
                "Delivered source_id=%s message_id=%s destination_id=%s job_id=%s",
                source,
                original.id,
                destination,
                job,
            )
            return MessageStatus.SUCCESS, sent_id
        except Exception as exc:
            record_result(
                job,
                source,
                original.id,
                destination,
                MessageStatus.FAILED,
                error=FRIENDLY_ERRORS[classify_error(exc)],
            )
            if classify_error(exc) not in {
                ForwardErrorType.UNKNOWN,
                ForwardErrorType.NETWORK_ERROR,
            }:
                clear_delivery_marker(source, original.id, destination)
            raise


async def fan_out(client, original, source, routes, signature, prepare, sender):
    # Caller holds the source-message lock through preparation, review lookup and delivery.
    outcomes = {}
    pending = []
    with get_session() as session:
        for destination, job in routes:
            if ForwardedMessageRepository.exists(session, source, original.id, destination):
                outcomes[destination] = MessageStatus.DUPLICATE
            else:
                pending.append((destination, job))
    for destination, job in routes:
        if destination in outcomes:
            record_result(job, source, original.id, destination, MessageStatus.DUPLICATE)
    if not pending:
        return outcomes
    existing = review_store.find_for_message(source, original.id)
    if existing and existing.status in {"pending", "sending", "uncertain", "rejected", "sent"}:
        existing = review_store.enqueue_routes(original, source, pending, existing.reason)
        if existing.status == "rejected":
            status, error = MessageStatus.SKIPPED, "رد شده توسط مدیر"
        else:
            status, error = MessageStatus.FAILED, "در انتظار تصمیم مدیر"
        for destination, job in pending:
            record_result(job, source, original.id, destination, status, error=error)
            outcomes[destination] = status
        return outcomes
    try:
        prepared = await prepare(original, source, signature)
    except (AIReviewRequired, AIProcessingError) as exc:
        reason = str(exc) if isinstance(exc, AIReviewRequired) else "service_unavailable"
        review_store.enqueue_routes(original, source, pending, reason)
        for destination, job in pending:
            record_result(
                job,
                source,
                original.id,
                destination,
                MessageStatus.FAILED,
                error="در انتظار تصمیم مدیر",
            )
            outcomes[destination] = MessageStatus.FAILED
        return outcomes
    for destination, job in pending:
        if prepared is None:
            status = MessageStatus.SKIPPED
            record_result(
                job, source, original.id, destination, status, error="حذف شده توسط هوش مصنوعی"
            )
        else:
            try:
                status, _ = await deliver(
                    client, original, source, destination, job, prepared, sender
                )
            except Exception as exc:
                error_type = classify_error(exc)
                logger.error(
                    "Send failed source_id=%s message_id=%s destination_id=%s job_id=%s type=%s",
                    source,
                    original.id,
                    destination,
                    job,
                    type(exc).__name__,
                )
                status = MessageStatus.FAILED
                record_result(
                    job, source, original.id, destination, status, error=FRIENDLY_ERRORS[error_type]
                )
                if error_type in {ForwardErrorType.UNKNOWN, ForwardErrorType.NETWORK_ERROR}:
                    row = review_store.enqueue_routes(original, source, pending, "send_uncertain")
                    review_store.set_status(row.id, "uncertain")
        outcomes[destination] = status
    return outcomes
