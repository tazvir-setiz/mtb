from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from telethon import TelegramClient
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
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository

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
    ForwardErrorType.PROTECTED_CONTENT: "🔒 محتوای این پیام محافظت‌شده و قابل Forward نیست",
    ForwardErrorType.NETWORK_ERROR: "🌐 خطای شبکه",
    ForwardErrorType.UNKNOWN: "⚠️ خطای نامشخص",
}


def classify_error(exc: Exception) -> ForwardErrorType:
    if isinstance(exc, FloodWaitError):
        return ForwardErrorType.FLOOD_WAIT
    if isinstance(exc, MessageIdInvalidError):
        return ForwardErrorType.MESSAGE_NOT_FOUND
    if isinstance(exc, (ChatAdminRequiredError, ChatWriteForbiddenError)):
        return ForwardErrorType.PERMISSION_DENIED
    if isinstance(exc, ChatForwardsRestrictedError):
        return ForwardErrorType.PROTECTED_CONTENT
    if isinstance(exc, UserBannedInChannelError):
        return ForwardErrorType.FORBIDDEN
    if isinstance(exc, (ValueError,)) and "Cannot find" in str(exc):
        return ForwardErrorType.CHAT_NOT_FOUND
    if isinstance(exc, (ConnectionError, OSError)):
        return ForwardErrorType.NETWORK_ERROR
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


async def forward_range(
    client: TelegramClient,
    job_id: int,
    source_channel_id: int,
    destination_channel_id: int,
    message_ids: list[int],
    on_progress: ProgressCallback | None = None,
) -> None:
    """
    پیام‌های message_ids را از source_channel_id به destination_channel_id
    به‌صورت Forward واقعی منتقل می‌کند. نتیجه هر پیام در دیتابیس ثبت می‌شود.
    """
    _stop_flags.pop(job_id, None)
    total = len(message_ids)
    processed = success = skipped = failed = 0

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job:
            ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)

    last_update = 0.0
    loop = asyncio.get_event_loop()

    for msg_id in message_ids:
        if _should_stop(job_id):
            with get_session() as session:
                job = ForwardJobRepository.get(session, job_id)
                if job:
                    ForwardJobRepository.update_status(session, job, JobStatus.PAUSED)
            if on_progress:
                await on_progress(
                    ProgressSnapshot(job_id, total, processed, success, skipped, failed, stopped=True)
                )
            return

        with get_session() as session:
            already = ForwardedMessageRepository.exists(
                session, source_channel_id, msg_id, destination_channel_id
            )
        if already:
            skipped += 1
            processed += 1
            with get_session() as session:
                job = ForwardJobRepository.get(session, job_id)
                if job:
                    ForwardJobRepository.increment(session, job, skipped=1, last_message_id=msg_id)
                ForwardedMessageRepository.record(
                    session,
                    job_id,
                    source_channel_id,
                    msg_id,
                    destination_channel_id,
                    MessageStatus.DUPLICATE,
                )
        else:
            try:
                result = await client.forward_messages(
                    entity=destination_channel_id,
                    messages=msg_id,
                    from_peer=source_channel_id,
                )
                dest_msg = result[0] if isinstance(result, list) else result
                dest_id = getattr(dest_msg, "id", None)
                success += 1
                with get_session() as session:
                    job = ForwardJobRepository.get(session, job_id)
                    if job:
                        ForwardJobRepository.increment(
                            session, job, success=1, last_message_id=msg_id
                        )
                    ForwardedMessageRepository.record(
                        session,
                        job_id,
                        source_channel_id,
                        msg_id,
                        destination_channel_id,
                        MessageStatus.SUCCESS,
                        destination_message_id=dest_id,
                    )
                logger.info("Message forwarded: %s -> %s", msg_id, dest_id)
            except FloodWaitError as exc:
                logger.warning("FloodWait: sleeping %s seconds", exc.seconds)
                if on_progress:
                    await on_progress(
                        ProgressSnapshot(job_id, total, processed, success, skipped, failed)
                    )
                await asyncio.sleep(exc.seconds + 1)
                # پیام فعلی را دوباره تلاش کن (بدون افزایش processed)
                try:
                    result = await client.forward_messages(
                        entity=destination_channel_id, messages=msg_id, from_peer=source_channel_id
                    )
                    dest_msg = result[0] if isinstance(result, list) else result
                    success += 1
                    with get_session() as session:
                        job = ForwardJobRepository.get(session, job_id)
                        if job:
                            ForwardJobRepository.increment(
                                session, job, success=1, last_message_id=msg_id
                            )
                        ForwardedMessageRepository.record(
                            session,
                            job_id,
                            source_channel_id,
                            msg_id,
                            destination_channel_id,
                            MessageStatus.SUCCESS,
                            destination_message_id=getattr(dest_msg, "id", None),
                        )
                except Exception as retry_exc:  # noqa: BLE001
                    failed += 1
                    err_type = classify_error(retry_exc)
                    logger.error("Message forwarding failed after FloodWait: %s", retry_exc)
                    with get_session() as session:
                        job = ForwardJobRepository.get(session, job_id)
                        if job:
                            ForwardJobRepository.increment(
                                session, job, failed=1, last_message_id=msg_id
                            )
                        ForwardedMessageRepository.record(
                            session,
                            job_id,
                            source_channel_id,
                            msg_id,
                            destination_channel_id,
                            MessageStatus.FAILED,
                            error=FRIENDLY_ERRORS[err_type],
                        )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                err_type = classify_error(exc)
                logger.error("Message forwarding failed: %s (%s)", exc, err_type)
                with get_session() as session:
                    job = ForwardJobRepository.get(session, job_id)
                    if job:
                        ForwardJobRepository.increment(session, job, failed=1, last_message_id=msg_id)
                    ForwardedMessageRepository.record(
                        session,
                        job_id,
                        source_channel_id,
                        msg_id,
                        destination_channel_id,
                        MessageStatus.FAILED,
                        error=FRIENDLY_ERRORS[err_type],
                    )
            processed += 1

        now = loop.time()
        if on_progress and (now - last_update >= settings.progress_update_interval or processed == total):
            last_update = now
            await on_progress(ProgressSnapshot(job_id, total, processed, success, skipped, failed))

        await asyncio.sleep(settings.forward_delay)

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if job:
            ForwardJobRepository.update_status(session, job, JobStatus.COMPLETED)
    logger.info("Forward job completed: job_id=%s success=%s failed=%s skipped=%s",
                job_id, success, failed, skipped)


async def retry_failed(
    client: TelegramClient,
    job_id: int,
    on_progress: ProgressCallback | None = None,
) -> None:
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        if not job:
            return
        failed_records = ForwardedMessageRepository.failed_for_job(session, job_id)
        message_ids = [r.source_message_id for r in failed_records]
        source_id = job.source_channel_id
        dest_id = job.destination_channel_id

    if not message_ids:
        return
    await forward_range(client, job_id, source_id, dest_id, message_ids, on_progress)
