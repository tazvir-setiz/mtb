"""
Auto-Forward پیام‌های جدید.

با فعال بودن این حالت، به‌محض انتشار پیام جدید در کانال مبدأ، همان لحظه
با Telethon Event (events.NewMessage) دریافت و به کانال مقصد Forward واقعی
می‌شود؛ نیازی به فشردن دکمه در Dashboard نیست.

نکته مهم: این حالت پیام‌های جاافتاده حین خاموش بودن ربات را Forward نمی‌کند؛
فقط پیام‌هایی که از لحظه روشن (یا فعال‌سازی مجدد) به بعد در کانال مبدأ
منتشر می‌شوند پردازش خواهند شد. برای پیام‌های قبلی از «انتقال بازه» یا
«انتخاب Message ID» در منوی «انتقال پیام‌ها» استفاده کنید.
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
from app.telegram.forward_service import FRIENDLY_ERRORS, classify_error

logger = logging.getLogger(__name__)

SETTING_KEY = "auto_forward_enabled"

# Marker مخصوص Job مربوط به حالت Auto-Forward (برای تمایز از Jobهای دستی)
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
    """
    یک ForwardJob دائمی مخصوص حالت Auto-Forward برمی‌گرداند (برای ثبت
    ForwardedMessageها استفاده می‌شود) یا در صورت نبود، آن را می‌سازد.
    """
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
    if already:
        return

    try:
        result = await event.client.forward_messages(
            entity=destination_id, messages=msg_id, from_peer=source_id
        )
        dest_msg = result[0] if isinstance(result, list) else result
        dest_id = getattr(dest_msg, "id", None)
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
    """
    Event Handler را روی کانال مبدأ فعلی ثبت می‌کند.
    اگر کانال مبدأ/مقصد تنظیم نشده باشند، False برمی‌گرداند.
    """
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
    """Auto-Forward را فعال می‌کند و در Settings ذخیره می‌کند."""
    started = await start_listener(client)
    if started:
        _set_enabled(True)
    return started


async def disable(client: TelegramClient) -> None:
    """Auto-Forward را غیرفعال می‌کند و در Settings ذخیره می‌کند."""
    await stop_listener(client)
    _set_enabled(False)


async def sync_on_startup(client: TelegramClient) -> None:
    """
    در استارت برنامه صدا زده می‌شود: اگر قبلاً Auto-Forward فعال بوده،
    دوباره Listener را (فقط برای پیام‌های از این لحظه به بعد) ثبت می‌کند.
    پیام‌های منتشرشده حین خاموش بودن ربات، عمداً Forward نمی‌شوند.
    """
    if is_enabled():
        started = await start_listener(client)
        if not started:
            # کانال‌ها هنوز تنظیم نشده‌اند؛ وضعیت را خاموش نگه دار
            _set_enabled(False)
