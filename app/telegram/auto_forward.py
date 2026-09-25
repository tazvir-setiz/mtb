"""
Auto-Forward پیام‌های جدید.
"""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient, events
from telethon.extensions import html as telethon_html

from app.database.database import get_session
from app.database.models import ChannelType, JobStatus, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.telegram.forward_service import FRIENDLY_ERRORS, classify_error, ForwardErrorType
from app.services.ai_service import apply_ai_guardrails

logger = logging.getLogger(__name__)

SETTING_KEY = "auto_forward_enabled"
_AUTO_JOB_MARKER = -1

_handler = None  # type: ignore[var-annotated]
_registered_client: TelegramClient | None = None

# 👈 این قفل اضافه شد تا پیام‌ها دقیقاً به ترتیب و یکی‌یکی پردازش شوند
_processing_lock = asyncio.Lock()


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
            source_channel_id=source_id,
            destination_channel_id=destination_id,
            start_message_id=_AUTO_JOB_MARKER,
            end_message_id=_AUTO_JOB_MARKER,
            total_messages=0,
        )
        ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)
        return job.id


async def _on_new_message(event, source_id: int, destination_id: int, job_id: int) -> None:  # noqa: ANN001
    # 👈 قفل کردن اجرای همزمان: پیام‌ها منتظر می‌مانند تا کار پیام قبلی کاملاً تمام شود
    async with _processing_lock:
        msg_id = event.message.id
        logger.info("Auto-forward: New message detected (ID: %d)", msg_id)

        with get_session() as session:
            already = ForwardedMessageRepository.exists(session, source_id, msg_id, destination_id)
            signature = SettingsRepository.get(session, "signature_text")

        if already:
            logger.debug("Auto-forward: Message %d already exists. Skipping.", msg_id)
            return

        try:
            if getattr(event.message, 'poll', None):
                logger.info("Auto-forward: Message %d is a poll. Forwarding directly.", msg_id)
                result = await event.client.forward_messages(entity=destination_id, messages=msg_id, from_peer=source_id, drop_author=True)
                dest_msg = result[0] if isinstance(result, list) else result
            else:
                current_html = telethon_html.unparse(event.message.message or "", event.message.entities or [])
                processed_html = await apply_ai_guardrails(current_html)

                if processed_html == "__DROP__":
                    logger.warning("Auto-forward: Message %d skipped by AI Guardrails.", msg_id)
                    with get_session() as session:
                        ForwardedMessageRepository.record(
                            session, job_id, source_id, msg_id, destination_id,
                            MessageStatus.SKIPPED, error="حذف شده توسط هوش مصنوعی"
                        )
                    return

                if signature:
                    separator = "\n\n" if processed_html.strip() else ""
                    processed_html += separator + signature

                media_to_send = event.message.media
                if media_to_send and type(media_to_send).__name__ == "MessageMediaWebPage":
                    media_to_send = None

                dest_msg = await event.client.send_message(
                    entity=destination_id,
                    message=processed_html,
                    file=media_to_send,
                    parse_mode='html',
                    link_preview=False
                )

            dest_id = getattr(dest_msg, "id", None)

            with get_session() as session:
                ForwardedMessageRepository.record(
                    session, job_id, source_id, msg_id, destination_id,
                    MessageStatus.SUCCESS, destination_message_id=dest_id,
                )
            logger.info("Auto-forward: Message %d -> %d successfully processed and sent.", msg_id, dest_id)

        except Exception as exc:  # noqa: BLE001
            err_type = classify_error(exc)
            if err_type == ForwardErrorType.UNKNOWN:
                logger.exception("Auto-forward: Unknown error processing message %d", msg_id)
            else:
                logger.error("Auto-forward failed for message %d: %s (%s)", msg_id, str(exc), err_type)

            with get_session() as session:
                ForwardedMessageRepository.record(
                    session, job_id, source_id, msg_id, destination_id,
                    MessageStatus.FAILED, error=FRIENDLY_ERRORS[err_type],
                )


async def start_listener(client: TelegramClient) -> bool:
    global _handler, _registered_client

    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)

    if source is None or destination is None:
        logger.warning("Auto-forward listener cannot start: Source or Destination not configured.")
        return False

    await stop_listener(client)

    source_id = source.telegram_id
    destination_id = destination.telegram_id
    job_id = _get_auto_job_id(source_id, destination_id)

    async def handler(event):  # noqa: ANN001
        await _on_new_message(event, source_id, destination_id, job_id)

    client.add_event_handler(handler, events.NewMessage(chats=source_id))
    _handler = handler
    _registered_client = client
    logger.info("Auto-forward listener started successfully (Source: %s -> Dest: %s)", source_id, destination_id)
    return True


async def stop_listener(client: TelegramClient) -> None:
    global _handler, _registered_client
    if _handler is not None and _registered_client is not None:
        _registered_client.remove_event_handler(_handler)
        logger.info("Auto-forward listener stopped.")
    _handler = None
    _registered_client = None


async def enable(client: TelegramClient) -> bool:
    started = await start_listener(client)
    if started: _set_enabled(True)
    return started


async def disable(client: TelegramClient) -> None:
    await stop_listener(client)
    _set_enabled(False)


async def sync_on_startup(client: TelegramClient) -> None:
    if is_enabled():
        logger.info("Auto-forward was enabled previously. Attempting to restart listener...")
        if not await start_listener(client):
            _set_enabled(False)