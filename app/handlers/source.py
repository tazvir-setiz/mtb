from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import ChannelRepository
from app.handlers.states import KEY_PENDING_CHANNEL, KEY_PENDING_CHANNEL_KIND, State, set_state
from app.telegram import auto_forward
from app.telegram.channel_service import (
    ChannelAccessError,
    resolve_channel,
    verify_destination_permissions,
)
from app.telegram.client import ensure_started
from app.ui import keyboards, messages

logger = logging.getLogger(__name__)

_TYPE_MAP = {"source": ChannelType.SOURCE, "destination": ChannelType.DESTINATION}
_STATE_MAP = {"source": State.SOURCE_CHANNEL, "destination": State.DESTINATION_CHANNEL}


async def show_channel_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str
) -> None:
    channel_type = _TYPE_MAP[kind]
    with get_session() as session:
        channel = ChannelRepository.get_by_type(session, channel_type)
    text = messages.ask_channel(kind, channel.title if channel else None)
    context.user_data[KEY_PENDING_CHANNEL_KIND] = kind
    context.user_data.pop(KEY_PENDING_CHANNEL, None)
    set_state(context.user_data, _STATE_MAP[kind])
    await update.callback_query.message.reply_text(
        text, reply_markup=keyboards.cancel_only(force_reply=True)
    )


async def handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kind = context.user_data.get(KEY_PENDING_CHANNEL_KIND)
    if kind not in _TYPE_MAP:
        return
    context.user_data.pop(KEY_PENDING_CHANNEL, None)
    raw = update.message.text.strip()

    try:
        client = await ensure_started()
        if kind == "destination":
            info = await verify_destination_permissions(client, raw)
        else:
            info = await resolve_channel(client, raw)
    except ChannelAccessError as exc:
        if kind == "destination" and "Administrator" in str(exc):
            await update.message.reply_text(
                messages.PERMISSION_ERROR, reply_markup=keyboards.destination_retry()
            )
        else:
            await update.message.reply_text(str(exc), reply_markup=keyboards.cancel_only())
        return
    except Exception:  # noqa: BLE001
        logger.exception("Channel resolution failed")
        await update.message.reply_text(
            messages.CHANNEL_NOT_FOUND, reply_markup=keyboards.cancel_only()
        )
        return

    text = messages.channel_confirmed(kind, info.title, info.telegram_id, info.username)
    prefix = "source" if kind == "source" else "destination"
    confirmation = await update.message.reply_text(
        text, reply_markup=keyboards.channel_confirm(prefix)
    )
    context.user_data[KEY_PENDING_CHANNEL] = {
        "kind": kind,
        "telegram_id": info.telegram_id,
        "title": info.title,
        "username": info.username,
        "message_id": confirmation.message_id,
    }


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str) -> None:
    from app.handlers.dashboard import show_dashboard

    pending = context.user_data.get(KEY_PENDING_CHANNEL)
    if (
        not pending
        or pending["kind"] != kind
        or (pending["message_id"] != update.callback_query.message.message_id)
    ):
        await update.callback_query.message.reply_text(
            "این تأیید منقضی شده است. کانال را دوباره انتخاب کنید."
        )
        return
    with get_session() as session:
        ChannelRepository.upsert(
            session,
            telegram_id=pending["telegram_id"],
            title=pending["title"],
            channel_type=_TYPE_MAP[kind],
            username=pending["username"],
        )
    context.user_data.pop(KEY_PENDING_CHANNEL, None)
    if auto_forward.is_enabled():
        try:
            refreshed = await auto_forward.refresh_listener(await ensure_started())
        except Exception:
            logger.exception("Could not reconnect auto-forward after channel change")
            await auto_forward.disable()
            refreshed = False
        if not refreshed:
            await update.callback_query.message.reply_text(
                "⚠️ کانال ذخیره شد، اما اتصال انتقال خودکار برقرار نشد و خاموش شد. "
                "پس از بررسی اتصال، دوباره آن را فعال کنید."
            )
    await show_dashboard(update, context, edit=True)


async def handle_change(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str) -> None:
    await show_channel_prompt(update, context, kind)


async def handle_destination_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.database.database import get_session as _gs

    with _gs() as session:
        channel = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)
    if not channel:
        await show_channel_prompt(update, context, "destination")
        return
    try:
        client = await ensure_started()
        info = await verify_destination_permissions(client, str(channel.telegram_id))
    except ChannelAccessError:
        await update.callback_query.edit_message_text(
            messages.PERMISSION_ERROR, reply_markup=keyboards.destination_retry()
        )
        return
    text = messages.channel_confirmed("destination", info.title, info.telegram_id, info.username)
    await update.callback_query.edit_message_text(
        text, reply_markup=keyboards.channel_confirm("destination")
    )
    context.user_data[KEY_PENDING_CHANNEL] = {
        "kind": "destination",
        "telegram_id": info.telegram_id,
        "title": info.title,
        "username": info.username,
        "message_id": update.callback_query.message.message_id,
    }


async def handle_destination_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 راهنمای تنظیم کانال مقصد\n\n"
        "۱. ربات (یا حساب متصل) را به کانال مقصد اضافه کنید.\n"
        "۲. از بخش Administrators کانال، آن را Administrator کنید.\n"
        "۳. دسترسی «ارسال پیام» (Post Messages) را فعال کنید.\n"
        "۴. دوباره «بررسی مجدد» را بزنید."
    )
    await update.callback_query.edit_message_text(text, reply_markup=keyboards.destination_retry())
