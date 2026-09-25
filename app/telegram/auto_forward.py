"""
Auto-Forward پیام‌های جدید.
"""
from __future__ import annotations

import logging

from telethon import TelegramClient, events

from app.database.database import get_session
from app.database.models import ChannelType, JobStatus, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.telegram.forward_service import FRIENDLY_ERRORS, append_signature_if_needed, classify_error

logger = logging.getLogger(__name__)

SETTING_KEY = "auto_forward_enabled"
_AUTO_JOB_MARKER = -1

_handler = None  # type: ignore[var-annotated]
_registered_client: TelegramClient | None = None


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
    msg_id = event.message.id

    with get_session() as session:
        already = ForwardedMessageRepository.exists(session, source_id, msg_id, destination_id)
        signature = SettingsRepository.get(session, "signature_text")

    if already:
        return

    try:
        result = await event.client.forward_messages(
            entity=destination_id,
            messages=msg_id,
            from_peer=source_id,
            drop_author=True,
        )
        dest_msg = result[0] if isinstance(result, list) else result
        dest_id = getattr(dest_msg, "id", None)

        # الصاق امضا
        if signature and dest_id:
            await append_signature_if_needed(event.client, destination_id, dest_msg, signature)

        with get_session() as session:
            ForwardedMessageRepository.record(
                session,
                job_id,
                source_id,
                msg_id,
                destination_id,
                MessageStatus.SUCCESS,
                destination_message_id=dest_id,
            )
        logger.info("Auto-forward: message %s -> %s", msg_id, dest_id)
    except Exception as exc:  # noqa: BLE001
        err_type = classify_error(exc)
        logger.error("Auto-forward failed for message %s: %s (%s)", msg_id, exc, err_type)
        with get_session() as session:
            ForwardedMessageRepository.record(
                session,
                job_id,
                source_id,
                msg_id,
                destination_id,
                MessageStatus.FAILED,
                error=FRIENDLY_ERRORS[err_type],
            )


async def start_listener(client: TelegramClient) -> bool:
    global _handler, _registered_client

    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)

    if source is None or destination is None:
        logger.warning("Auto-forward: کانال مبدأ یا مقصد تنظیم نشده است.")
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
    logger.info("Auto-forward فعال شد: source=%s -> destination=%s", source_id, destination_id)
    return True


async def stop_listener(client: TelegramClient) -> None:
    global _handler, _registered_client
    if _handler is not None and _registered_client is not None:
        _registered_client.remove_event_handler(_handler)
        logger.info("Auto-forward غیرفعال شد.")
    _handler = None
    _registered_client = None


async def enable(client: TelegramClient) -> bool:
    started = await start_listener(client)
    if started:
        _set_enabled(True)
    return started


async def disable(client: TelegramClient) -> None:
    await stop_listener(client)
    _set_enabled(False)


async def sync_on_startup(client: TelegramClient) -> None:
    if is_enabled():
        started = await start_listener(client)
        if not started:
            _set_enabled(False)