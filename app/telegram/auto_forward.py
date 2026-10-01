from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from contextlib import asynccontextmanager

from telethon import TelegramClient, events

from app.database.database import get_session
from app.database.models import ChannelType, JobStatus, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.log_context import traced
from app.services import review_store
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.message_locks import message_lock
from app.telegram.forward_errors import FRIENDLY_ERRORS, ForwardErrorType, classify_error
from app.telegram.message_sender import prepare_message, send_prepared_message

logger = logging.getLogger(__name__)

SETTING_KEY = "auto_forward_enabled"
_AUTO_JOB_MARKER = -1

_handler = None  # type: ignore[var-annotated]
_registered_client: TelegramClient | None = None
_processing_lock = asyncio.Lock()
_waiting = 0
_counts = Counter()


def status_snapshot():
    return dict(
        listener_active=_handler is not None,
        waiting=_waiting,
        processing=_processing_lock.locked(),
        **_counts,
    )


@asynccontextmanager
async def processing_slot():
    global _waiting
    started = time.monotonic()
    _waiting += 1
    _counts["received"] += 1
    try:
        await _processing_lock.acquire()
    finally:
        _waiting -= 1
    try:
        yield
    finally:
        _processing_lock.release()
        logger.info(
            "Processing finished total_elapsed=%.2fs waiting=%d",
            time.monotonic() - started,
            _waiting,
        )


def is_enabled() -> bool:
    with get_session() as session:
        return SettingsRepository.get(session, SETTING_KEY, default="0") == "1"


def _set_enabled(value: bool) -> None:
    with get_session() as session:
        SettingsRepository.set(session, SETTING_KEY, "1" if value else "0")


def _get_auto_job_id(source_id: int, destination_id: int) -> int:
    with get_session() as session:
        job = ForwardJobRepository.create(
            session,
            source_id,
            destination_id,
            _AUTO_JOB_MARKER,
            _AUTO_JOB_MARKER,
            0,
        )
        ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)
        return job.id


def _record(
    job_id,
    source_id,
    msg_id,
    destination_id,
    status,
    *,
    destination_message_id=None,
    error=None,
):
    with get_session() as session:
        ForwardedMessageRepository.record(
            session,
            job_id,
            source_id,
            msg_id,
            destination_id,
            status,
            destination_message_id=destination_message_id,
            error=error,
        )


@traced
async def _on_new_message(
    event,
    source_id: int,
    routes: list[tuple[int, int]],
    *,
    listener=None,
) -> None:
    async with processing_slot():
        if listener is not None and listener is not _handler:
            _counts["stale"] += 1
            return

        msg_id = event.message.id
        with get_session() as session:
            signature = SettingsRepository.get(session, "signature_text")
            pending_routes = [
                (destination_id, job_id)
                for destination_id, job_id in routes
                if not ForwardedMessageRepository.exists(
                    session,
                    source_id,
                    msg_id,
                    destination_id,
                )
            ]

        if not pending_routes:
            _counts["duplicates"] += len(routes)
            return

        existing_review = review_store.find_for_message(source_id, msg_id)
        if existing_review and existing_review.status in {
            "pending",
            "sending",
            "uncertain",
        }:
            _counts["review_pending"] += 1
            return
        if existing_review and existing_review.status == "rejected":
            for destination_id, job_id in pending_routes:
                _record(
                    job_id,
                    source_id,
                    msg_id,
                    destination_id,
                    MessageStatus.SKIPPED,
                    error="رد شده توسط مدیر",
                )
            return

        try:
            prepared = await prepare_message(event.message, source_id, signature)
        except (AIReviewRequired, AIProcessingError) as exc:
            reason = (
                str(exc)
                if isinstance(exc, AIReviewRequired)
                else "service_unavailable"
            )
            review_store.enqueue_routes(
                event.message,
                source_id,
                pending_routes,
                reason,
            )
            _counts["review"] += 1
            return

        if prepared is None:
            for destination_id, job_id in pending_routes:
                _record(
                    job_id,
                    source_id,
                    msg_id,
                    destination_id,
                    MessageStatus.SKIPPED,
                    error="حذف شده توسط هوش مصنوعی",
                )
            _counts["skipped"] += len(pending_routes)
            return

        for destination_id, job_id in pending_routes:
            async with message_lock(source_id, msg_id, destination_id):
                with get_session() as session:
                    if ForwardedMessageRepository.exists(
                        session,
                        source_id,
                        msg_id,
                        destination_id,
                    ):
                        _counts["duplicates"] += 1
                        continue

                try:
                    sent = await send_prepared_message(
                        event.client,
                        event.message,
                        source_id,
                        destination_id,
                        prepared,
                    )
                    destination_message_id = getattr(sent, "id", None)
                    _record(
                        job_id,
                        source_id,
                        msg_id,
                        destination_id,
                        MessageStatus.SUCCESS,
                        destination_message_id=destination_message_id,
                    )
                    _counts["sent"] += 1
                except Exception as exc:
                    err_type = classify_error(exc)
                    if err_type == ForwardErrorType.UNKNOWN:
                        logger.exception(
                            "Auto-forward failed message=%d destination=%s",
                            msg_id,
                            destination_id,
                        )
                    else:
                        logger.error(
                            "Auto-forward failed message=%d destination=%s reason=%s",
                            msg_id,
                            destination_id,
                            err_type.value,
                        )
                    _record(
                        job_id,
                        source_id,
                        msg_id,
                        destination_id,
                        MessageStatus.FAILED,
                        error=FRIENDLY_ERRORS[err_type],
                    )
                    _counts["failed"] += 1


async def start_listener(client: TelegramClient) -> bool:
    global _handler, _registered_client

    await stop_listener(client)
    with get_session() as session:
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(
            session,
            ChannelType.DESTINATION,
        )

    if not sources or not destinations:
        return False

    source_ids = [channel.telegram_id for channel in sources]
    destination_ids = [channel.telegram_id for channel in destinations]
    route_map = {
        source_id: [
            (
                destination_id,
                _get_auto_job_id(source_id, destination_id),
            )
            for destination_id in destination_ids
        ]
        for source_id in source_ids
    }

    async def handler(event):
        source_id = getattr(event, "chat_id", None)
        if source_id not in route_map:
            return
        await _on_new_message(
            event,
            source_id,
            route_map[source_id],
            listener=handler,
        )

    client.add_event_handler(handler, events.NewMessage(chats=source_ids))
    _handler = handler
    _registered_client = client
    logger.info(
        "Auto-forward listener started sources=%s destinations=%s",
        source_ids,
        destination_ids,
    )
    return True


async def stop_listener(client: TelegramClient | None = None) -> None:
    global _handler, _registered_client
    if _handler is not None and _registered_client is not None:
        _registered_client.remove_event_handler(_handler)
    _handler = None
    _registered_client = None


async def enable(client: TelegramClient) -> bool:
    try:
        started = await start_listener(client)
    except Exception:
        _set_enabled(False)
        raise
    _set_enabled(started)
    return started


async def disable(client: TelegramClient | None = None) -> None:
    await stop_listener(client)
    _set_enabled(False)


async def sync_on_startup(client: TelegramClient) -> bool:
    return await refresh_listener(client)


async def refresh_listener(client: TelegramClient) -> bool:
    if not is_enabled():
        return False
    try:
        return await enable(client)
    except Exception:
        logger.exception("Could not refresh auto-forward listener")
        await disable(client)
        return False
