from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from app.config import settings
from app.database.database import get_session
from app.database.models import JobStatus, MessageStatus
from app.database.repository import (
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.services.forward_results import record_result, set_job_status
from app.telegram.forward_errors import FRIENDLY_ERRORS, ForwardErrorType, classify_error
from app.telegram.forward_progress import ProgressCallback, ProgressSnapshot
from app.telegram.message_sender import fetch_and_send_message

logger = logging.getLogger(__name__)

_stop_flags: dict[int, bool] = {}


def request_stop(job_id: int) -> None:
    _stop_flags[job_id] = True


async def _send_with_retry(
    client: TelegramClient,
    msg_id: int,
    source_id: int,
    destination_id: int,
    signature: str | None,
    snapshot: ProgressSnapshot,
    on_progress: ProgressCallback | None,
) -> Message | None:
    try:
        return await fetch_and_send_message(client, msg_id, source_id, destination_id, signature)
    except FloodWaitError as exc:
        logger.warning("FloodWait for message %d: waiting %d seconds.", msg_id, exc.seconds)
        if on_progress:
            await on_progress(snapshot)
        await asyncio.sleep(exc.seconds + 1)
        return await fetch_and_send_message(client, msg_id, source_id, destination_id, signature)


async def forward_range(
    client: TelegramClient,
    job_id: int,
    source_channel_id: int,
    destination_channel_id: int,
    message_ids: list[int],
    on_progress: ProgressCallback | None = None,
) -> None:
    _stop_flags.pop(job_id, None)
    total = len(message_ids)
    processed = success = skipped = failed = 0
    set_job_status(job_id, JobStatus.RUNNING)

    with get_session() as session:
        signature = SettingsRepository.get(session, "signature_text")

    last_update = 0.0
    loop = asyncio.get_running_loop()

    for msg_id in message_ids:
        if _stop_flags.pop(job_id, False):
            logger.info("Job %d manually stopped.", job_id)
            set_job_status(job_id, JobStatus.PAUSED)
            if on_progress:
                await on_progress(
                    ProgressSnapshot(
                        job_id, total, processed, success, skipped, failed, stopped=True
                    )
                )
            return

        with get_session() as session:
            already = ForwardedMessageRepository.exists(
                session, source_channel_id, msg_id, destination_channel_id
            )

        destination_message_id = None
        error = None
        if already:
            status = MessageStatus.DUPLICATE
            logger.debug("Message %d skipped (already forwarded).", msg_id)
        else:
            try:
                dest_msg = await _send_with_retry(
                    client,
                    msg_id,
                    source_channel_id,
                    destination_channel_id,
                    signature,
                    ProgressSnapshot(job_id, total, processed, success, skipped, failed),
                    on_progress,
                )
                if dest_msg is None:
                    status = MessageStatus.SKIPPED
                    error = "حذف شده توسط هوش مصنوعی"
                    logger.info("Message %d skipped by AI guardrails.", msg_id)
                else:
                    status = MessageStatus.SUCCESS
                    destination_message_id = getattr(dest_msg, "id", None)
                    logger.info(
                        "Message %d -> %s sent successfully.", msg_id, destination_message_id
                    )
            except Exception as exc:
                status = MessageStatus.FAILED
                error_type = classify_error(exc)
                error = FRIENDLY_ERRORS[error_type]
                if error_type == ForwardErrorType.UNKNOWN:
                    logger.exception("Unknown error while forwarding message %d", msg_id)
                else:
                    logger.error("Failed to forward message %d: %s (%s)", msg_id, exc, error_type)

        record_result(
            job_id,
            source_channel_id,
            msg_id,
            destination_channel_id,
            status,
            destination_message_id=destination_message_id,
            error=error,
        )
        success += int(status == MessageStatus.SUCCESS)
        failed += int(status == MessageStatus.FAILED)
        skipped += int(status in (MessageStatus.SKIPPED, MessageStatus.DUPLICATE))
        processed += 1

        now = loop.time()
        if on_progress and (
            now - last_update >= settings.progress_update_interval or processed == total
        ):
            last_update = now
            await on_progress(ProgressSnapshot(job_id, total, processed, success, skipped, failed))
        await asyncio.sleep(settings.forward_delay)

    _stop_flags.pop(job_id, None)
    set_job_status(job_id, JobStatus.COMPLETED)
    logger.info(
        "Job %d completed. Success: %d, Skipped: %d, Failed: %d",
        job_id,
        success,
        skipped,
        failed,
    )


async def retry_failed(
    client: TelegramClient,
    job_id: int,
    on_progress: ProgressCallback | None = None,
) -> None:
    logger.info("Initiating retry for failed messages of Job %d", job_id)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if not job:
            return
        failed_records = ForwardedMessageRepository.failed_for_job(session, job_id)
        message_ids = [record.source_message_id for record in failed_records]
        source_id = job.source_channel_id
        destination_id = job.destination_channel_id

    if not message_ids:
        logger.info("No failed messages found to retry for Job %d", job_id)
        return
    await forward_range(client, job_id, source_id, destination_id, message_ids, on_progress)
