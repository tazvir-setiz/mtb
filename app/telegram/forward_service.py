from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from telethon.errors import FloodWaitError, MessageIdInvalidError

from app.config import settings
from app.database.database import get_session
from app.database.models import ForwardedMessage, JobStatus, MessageStatus
from app.database.repository import (
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.log_context import traced
from app.services.fanout import fan_out
from app.services.forward_results import record_result, set_job_status
from app.services.message_locks import message_lock
from app.services.transfer_routes import failed_ids, job_routes
from app.telegram.forward_errors import FRIENDLY_ERRORS, classify_error
from app.telegram.forward_errors import ForwardErrorType as ForwardErrorType
from app.telegram.forward_progress import ProgressCallback, ProgressSnapshot
from app.telegram.message_sender import prepare_message, send_prepared_message

logger = logging.getLogger(__name__)
_stop_flags: dict[int, bool] = {}


def request_stop(job_id: int) -> None:
    _stop_flags[job_id] = True


async def report_progress(callback, snapshot):
    try:
        await callback(snapshot)
    except Exception as exc:
        logger.warning(
            "Progress notification failed job_id=%s type=%s; transfer continues",
            snapshot.job_id,
            type(exc).__name__,
        )


@traced
async def forward_range(
    client,
    job_id: int,
    source_channel_id: int,
    destination_channel_id: int,
    message_ids: list[int],
    on_progress: ProgressCallback | None = None,
    *,
    retry_only=False,
) -> None:
    _stop_flags.pop(job_id, None)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job is None:
            return
        if source_channel_id != job.source_channel_id:
            raise ValueError("Transfer source does not match persisted job")
        routes = job_routes(session, job)
        signature = SettingsRepository.get(session, "signature_text")
    for _, route_job in routes:
        set_job_status(route_job, JobStatus.RUNNING)
    message_ids = sorted(set(message_ids))
    selected_routes = {msg_id: routes for msg_id in message_ids}
    if retry_only:
        with get_session() as session:
            for msg_id in message_ids:
                skipped_destinations = set(
                    session.scalars(
                        select(ForwardedMessage.destination_channel_id).where(
                            ForwardedMessage.source_channel_id == source_channel_id,
                            ForwardedMessage.source_message_id == msg_id,
                            ForwardedMessage.status == MessageStatus.SKIPPED,
                        )
                    )
                )
                selected_routes[msg_id] = [
                    (destination, route_job)
                    for destination, route_job in routes
                    if destination not in skipped_destinations
                ]
    total = sum(len(value) for value in selected_routes.values())
    processed = success = skipped = failed = 0
    last_update = 0.0
    loop = asyncio.get_running_loop()

    async def send_with_retry(*args):
        try:
            return await send_prepared_message(*args)
        except FloodWaitError as exc:
            if on_progress:
                await report_progress(on_progress, snapshot())
            await asyncio.sleep(exc.seconds + 1)
            return await send_prepared_message(*args)

    def snapshot(stopped=False):
        return ProgressSnapshot(job_id, total, processed, success, skipped, failed, stopped)

    for msg_id in sorted(set(message_ids)):
        if _stop_flags.pop(job_id, False):
            for _, route_job in routes:
                set_job_status(route_job, JobStatus.PAUSED)
            if on_progress:
                await report_progress(on_progress, snapshot(True))
            return
        message_routes = selected_routes[msg_id]
        async with message_lock(source_channel_id, msg_id, None):
            with get_session() as session:
                all_sent = all(
                    ForwardedMessageRepository.exists(
                        session, source_channel_id, msg_id, destination
                    )
                    for destination, _ in message_routes
                )
            if all_sent:
                outcomes = {
                    destination: MessageStatus.DUPLICATE for destination, _ in message_routes
                }
                for destination, route_job in message_routes:
                    record_result(
                        route_job, source_channel_id, msg_id, destination, MessageStatus.DUPLICATE
                    )
            else:
                try:
                    try:
                        originals = await client.get_messages(source_channel_id, ids=[msg_id])
                    except FloodWaitError as exc:
                        if on_progress:
                            await report_progress(on_progress, snapshot())
                        await asyncio.sleep(exc.seconds + 1)
                        originals = await client.get_messages(source_channel_id, ids=[msg_id])
                    if not originals or not originals[0]:
                        raise MessageIdInvalidError(request=None)
                    outcomes = await fan_out(
                        client,
                        originals[0],
                        source_channel_id,
                        message_routes,
                        signature,
                        prepare_message,
                        send_with_retry,
                    )
                except Exception as exc:
                    logger.exception(
                        "Transfer preparation failed source_id=%s message_id=%s job_id=%s",
                        source_channel_id,
                        msg_id,
                        job_id,
                    )
                    outcomes = {}
                    for destination, route_job in message_routes:
                        with get_session() as session:
                            sent = ForwardedMessageRepository.exists(
                                session, source_channel_id, msg_id, destination
                            )
                        status = MessageStatus.DUPLICATE if sent else MessageStatus.FAILED
                        record_result(
                            route_job,
                            source_channel_id,
                            msg_id,
                            destination,
                            status,
                            error=FRIENDLY_ERRORS[classify_error(exc)],
                        )
                        outcomes[destination] = status
        for status in outcomes.values():
            success += int(status == MessageStatus.SUCCESS)
            failed += int(status == MessageStatus.FAILED)
            skipped += int(status in (MessageStatus.SKIPPED, MessageStatus.DUPLICATE))
            processed += 1
        now = loop.time()
        if on_progress and (
            now - last_update >= settings.progress_update_interval or processed == total
        ):
            last_update = now
            await report_progress(on_progress, snapshot())
        await asyncio.sleep(settings.forward_delay)
    _stop_flags.pop(job_id, None)
    for _, route_job in routes:
        set_job_status(route_job, JobStatus.COMPLETED)


async def retry_failed(client, job_id: int, on_progress: ProgressCallback | None = None) -> None:
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job is None:
            return
        routes = job_routes(session, job)
        message_ids = sorted(
            {mid for _, route_job in routes for mid in failed_ids(session, route_job)}
        )
    if message_ids:
        await forward_range(
            client,
            job_id,
            job.source_channel_id,
            job.destination_channel_id,
            message_ids,
            on_progress,
            retry_only=True,
        )
