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


async def show_channels(update, context, kind, removing=False):
    from app.handlers.states import reset
    from app.ui.buttons.channels import channel_management
    from app.ui.texts.channels import channel_list

    reset(context.user_data)
    with get_session() as session:
        channels = ChannelRepository.get_all_by_type(session, _TYPE_MAP[kind])
    from app.ui.callbacks import parse

    namespace, action, arg = parse(getattr(update.callback_query, "data", "") or "")
    page = (
        int(arg) if arg and arg.isdigit() and (namespace == "menu" or action == "removals") else 0
    )
    pages = max(1, (len(channels) + 9) // 10)
    page = min(page, pages - 1)
    visible = channels[page * 10 : (page + 1) * 10]
    await update.callback_query.edit_message_text(
        channel_list(kind, visible, offset=page * 10),
        reply_markup=channel_management(kind, visible, removing=removing, page=page, pages=pages),
    )


async def remove_channel(update, context, kind):
    from app.ui.callbacks import parse

    _, _, arg = parse(update.callback_query.data)
    if arg is None or not arg.lstrip("-").isdigit():
        return
    with get_session() as session:
        ChannelRepository.remove(session, _TYPE_MAP[kind], int(arg))
    await refresh_auto_forward(update)
    await show_channels(update, context, kind)


def remember_channel(user_data: dict, kind: str, info, message_id: int) -> None:
    user_data[KEY_PENDING_CHANNEL] = {
        "kind": kind,
        "telegram_id": info.telegram_id,
        "title": info.title,
        "username": info.username,
        "message_id": message_id,
    }


async def show_channel_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str
) -> None:
    channel_type = _TYPE_MAP[kind]
    with get_session() as session:
        channels = ChannelRepository.get_all_by_type(session, channel_type)
    text = messages.ask_channel(kind, f"{len(channels)} کانال" if channels else None)
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
    context.user_data["channel_input"] = raw

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
    except Exception:
        logger.exception("Channel resolution failed")
        await update.message.reply_text(
            messages.CHANNEL_NOT_FOUND, reply_markup=keyboards.cancel_only()
        )
        return

    text = messages.channel_confirmed(kind, info.title, info.telegram_id, info.username)
    confirmation = await update.message.reply_text(
        text, reply_markup=keyboards.channel_confirm(kind)
    )
    remember_channel(context.user_data, kind, info, confirmation.message_id)


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
    await refresh_auto_forward(update)
    await show_dashboard(update, context, edit=True)


async def refresh_auto_forward(update: Update) -> None:
    if not auto_forward.is_enabled():
        return
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


async def handle_change(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str) -> None:
    await show_channel_prompt(update, context, kind)


async def handle_destination_retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = context.user_data.get("channel_input")
    if not raw:
        await show_channel_prompt(update, context, "destination")
        return
    try:
        client = await ensure_started()
        info = await verify_destination_permissions(client, raw)
    except ChannelAccessError:
        await update.callback_query.edit_message_text(
            messages.PERMISSION_ERROR, reply_markup=keyboards.destination_retry()
        )
        return
    text = messages.channel_confirmed("destination", info.title, info.telegram_id, info.username)
    await update.callback_query.edit_message_text(
        text, reply_markup=keyboards.channel_confirm("destination")
    )
    remember_channel(
        context.user_data, "destination", info, update.callback_query.message.message_id
    )


async def handle_destination_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 راهنمای تنظیم کانال مقصد\n\n"
        "۱. ربات (یا حساب متصل) را به کانال مقصد اضافه کنید.\n"
        "۲. از بخش Administrators کانال، آن را Administrator کنید.\n"
        "۳. دسترسی «ارسال پیام» (Post Messages) را فعال کنید.\n"
        "۴. دوباره «بررسی مجدد» را بزنید."
    )
    await update.callback_query.edit_message_text(text, reply_markup=keyboards.destination_retry())
