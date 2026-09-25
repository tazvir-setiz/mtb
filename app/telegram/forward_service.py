from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from telethon import TelegramClient
from telethon.extensions import html as telethon_html
from telethon.tl.types import MessageMediaWebPage
from telethon.errors import (
    ChatAdminRequiredError,
    ChatForwardsRestrictedError,
    FloodWaitError,
    MessageIdInvalidError,
    UserBannedInChannelError,
)
from telethon.errors.rpcerrorlist import ChatWriteForbiddenError

from app.config import settings
from app.database.database import get_session
from app.database.models import JobStatus, MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository, SettingsRepository
from app.services.ai_service import apply_ai_guardrails

logger = logging.getLogger(__name__)


class ForwardErrorType(str, Enum):
    FLOOD_WAIT = "flood_wait"
    MESSAGE_NOT_FOUND = "message_not_found"
    CHAT_NOT_FOUND = "chat_not_found"
    PERMISSION_DENIED = "permission_denied"
    FORBIDDEN = "forbidden"
    PROTECTED_CONTENT = "protected_content"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


FRIENDLY_ERRORS: dict[ForwardErrorType, str] = {
    ForwardErrorType.FLOOD_WAIT: "⏳ محدودیت موقت Telegram (FloodWait)",
    ForwardErrorType.MESSAGE_NOT_FOUND: "⚠️ پیام یافت نشد یا حذف شده است",
    ForwardErrorType.CHAT_NOT_FOUND: "⚠️ کانال یافت نشد",
    ForwardErrorType.PERMISSION_DENIED: "⚠️ دسترسی کافی نیست",
    ForwardErrorType.FORBIDDEN: "⚠️ ارسال پیام مجاز نیست",
    ForwardErrorType.PROTECTED_CONTENT: "🔒 محتوای محافظت‌شده",
    ForwardErrorType.NETWORK_ERROR: "🌐 خطای شبکه",
    ForwardErrorType.UNKNOWN: "⚠️ خطای نامشخص",
}


def classify_error(exc: Exception) -> ForwardErrorType:
    if isinstance(exc, FloodWaitError): return ForwardErrorType.FLOOD_WAIT
    if isinstance(exc, MessageIdInvalidError): return ForwardErrorType.MESSAGE_NOT_FOUND
    if isinstance(exc, (ChatAdminRequiredError, ChatWriteForbiddenError)): return ForwardErrorType.PERMISSION_DENIED
    if isinstance(exc, ChatForwardsRestrictedError): return ForwardErrorType.PROTECTED_CONTENT
    if isinstance(exc, UserBannedInChannelError): return ForwardErrorType.FORBIDDEN
    if isinstance(exc, (ValueError,)) and "Cannot find" in str(exc): return ForwardErrorType.CHAT_NOT_FOUND
    if isinstance(exc, (ConnectionError, OSError)): return ForwardErrorType.NETWORK_ERROR
    return ForwardErrorType.UNKNOWN


@dataclass
class ProgressSnapshot:
    job_id: int
    total: int
    processed: int
    success: int
    skipped: int
    failed: int
    stopped: bool = False


ProgressCallback = Callable[[ProgressSnapshot], Awaitable[None]]

_stop_flags: dict[int, bool] = {}


def request_stop(job_id: int) -> None:
    _stop_flags[job_id] = True


def _should_stop(job_id: int) -> bool:
    return _stop_flags.get(job_id, False)


async def _process_and_send_message(client: TelegramClient, msg_id: int, source_id: int, dest_id: int,
                                    signature: str | None):
    msgs = await client.get_messages(source_id, ids=[msg_id])
    if not msgs or not msgs[0]:
        raise MessageIdInvalidError(request=None)

    original_msg = msgs[0]

    if getattr(original_msg, 'poll', None):
        logger.info("Message %d is a poll. Skipping AI and forwarding directly.", msg_id)
        result = await client.forward_messages(entity=dest_id, messages=msg_id, from_peer=source_id, drop_author=True)
        return result[0] if isinstance(result, list) else result

    current_html = telethon_html.unparse(original_msg.message or "", original_msg.entities or [])

    processed_html = await apply_ai_guardrails(current_html)

    if processed_html == "__DROP__":
        return None

    if signature:
        separator = "\n\n" if processed_html.strip() else ""
        processed_html += separator + signature

    media_to_send = original_msg.media
    if media_to_send and type(media_to_send).__name__ == "MessageMediaWebPage":
        media_to_send = None

    dest_msg = await client.send_message(
        entity=dest_id,
        message=processed_html,
        file=media_to_send,
        parse_mode='html',
        link_preview=False
    )
    return dest_msg


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

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job: ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)
        signature = SettingsRepository.get(session, "signature_text")

    last_update = 0.0
    loop = asyncio.get_event_loop()

    for msg_id in message_ids:
        if _should_stop(job_id):
            logger.info("Job %d manually stopped.", job_id)
            with get_session() as session:
                job = ForwardJobRepository.get(session, job_id)
                if job: ForwardJobRepository.update_status(session, job, JobStatus.PAUSED)
            if on_progress:
                await on_progress(ProgressSnapshot(job_id, total, processed, success, skipped, failed, stopped=True))
            return

        with get_session() as session:
            already = ForwardedMessageRepository.exists(session, source_channel_id, msg_id, destination_channel_id)

        if already:
            skipped += 1
            processed += 1
            with get_session() as session:
                job = ForwardJobRepository.get(session, job_id)
                if job: ForwardJobRepository.increment(session, job, skipped=1, last_message_id=msg_id)
                ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id, destination_channel_id,
                                                  MessageStatus.DUPLICATE)
            logger.debug("Message %d skipped (Already forwarded).", msg_id)
        else:
            try:
                dest_msg = await _process_and_send_message(client, msg_id, source_channel_id, destination_channel_id,
                                                           signature)

                if dest_msg is None:
                    skipped += 1
                    with get_session() as session:
                        job = ForwardJobRepository.get(session, job_id)
                        if job: ForwardJobRepository.increment(session, job, skipped=1, last_message_id=msg_id)
                        ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                          destination_channel_id, MessageStatus.SKIPPED,
                                                          error="حذف شده توسط هوش مصنوعی")
                    logger.info("Message %d skipped (Rejected by AI Guardrails).", msg_id)
                else:
                    dest_id = getattr(dest_msg, "id", None)
                    success += 1
                    with get_session() as session:
                        job = ForwardJobRepository.get(session, job_id)
                        if job: ForwardJobRepository.increment(session, job, success=1, last_message_id=msg_id)
                        ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                          destination_channel_id, MessageStatus.SUCCESS,
                                                          destination_message_id=dest_id)
                    logger.info("Message %d -> %d forwarded successfully.", msg_id, dest_id)

            except FloodWaitError as exc:
                logger.warning("FloodWait triggered. Sleeping for %d seconds...", exc.seconds)
                if on_progress:
                    await on_progress(ProgressSnapshot(job_id, total, processed, success, skipped, failed))
                await asyncio.sleep(exc.seconds + 1)

                try:
                    dest_msg = await _process_and_send_message(client, msg_id, source_channel_id,
                                                               destination_channel_id, signature)
                    if dest_msg is None:
                        skipped += 1
                        with get_session() as session:
                            job = ForwardJobRepository.get(session, job_id)
                            if job: ForwardJobRepository.increment(session, job, skipped=1, last_message_id=msg_id)
                            ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                              destination_channel_id, MessageStatus.SKIPPED,
                                                              error="حذف شده توسط هوش مصنوعی")
                    else:
                        dest_id = getattr(dest_msg, "id", None)
                        success += 1
                        with get_session() as session:
                            job = ForwardJobRepository.get(session, job_id)
                            if job: ForwardJobRepository.increment(session, job, success=1, last_message_id=msg_id)
                            ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                              destination_channel_id, MessageStatus.SUCCESS,
                                                              destination_message_id=dest_id)
                except Exception as retry_exc:  # noqa: BLE001
                    failed += 1
                    err_type = classify_error(retry_exc)
                    logger.exception("Failed to forward message %d after FloodWait.", msg_id)
                    with get_session() as session:
                        job = ForwardJobRepository.get(session, job_id)
                        if job: ForwardJobRepository.increment(session, job, failed=1, last_message_id=msg_id)
                        ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                          destination_channel_id, MessageStatus.FAILED,
                                                          error=FRIENDLY_ERRORS[err_type])

            except Exception as exc:  # noqa: BLE001
                failed += 1
                err_type = classify_error(exc)

                if err_type == ForwardErrorType.UNKNOWN:
                    logger.exception("Unknown error while forwarding message %d", msg_id)
                else:
                    logger.error("Failed to forward message %d: %s (Reason: %s)", msg_id, str(exc), err_type)

                with get_session() as session:
                    job = ForwardJobRepository.get(session, job_id)
                    if job: ForwardJobRepository.increment(session, job, failed=1, last_message_id=msg_id)
                    ForwardedMessageRepository.record(session, job_id, source_channel_id, msg_id,
                                                      destination_channel_id, MessageStatus.FAILED,
                                                      error=FRIENDLY_ERRORS[err_type])
            processed += 1

        now = loop.time()
        if on_progress and (now - last_update >= settings.progress_update_interval or processed == total):
            last_update = now
            await on_progress(ProgressSnapshot(job_id, total, processed, success, skipped, failed))

        await asyncio.sleep(settings.forward_delay)

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job: ForwardJobRepository.update_status(session, job, JobStatus.COMPLETED)
    logger.info("Job %d completed. Success: %d, Skipped: %d, Failed: %d", job_id, success, skipped, failed)


async def retry_failed(client: TelegramClient, job_id: int, on_progress: ProgressCallback | None = None) -> None:
    logger.info("Initiating retry for failed messages of Job %d", job_id)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if not job: return
        failed_records = ForwardedMessageRepository.failed_for_job(session, job_id)
        message_ids = [r.source_message_id for r in failed_records]
        source_id = job.source_channel_id
        dest_id = job.destination_channel_id

    if not message_ids:
        logger.info("No failed messages found to retry for Job %d", job_id)
        return
    await forward_range(client, job_id, source_id, dest_id, message_ids, on_progress)