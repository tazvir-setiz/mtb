from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import ChannelRepository
from app.handlers.states import KEY_PENDING_CHANNEL_KIND, State, set_state
from app.telegram.channel_service import ChannelAccessError, resolve_channel, verify_destination_permissions
from app.telegram.client import ensure_started
from app.ui import keyboards, messages

logger = logging.getLogger(__name__)

_TYPE_MAP = {"source": ChannelType.SOURCE, "destination": ChannelType.DESTINATION}
_STATE_MAP = {"source": State.SOURCE_CHANNEL, "destination": State.DESTINATION_CHANNEL}


async def show_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str) -> None:
    channel_type = _TYPE_MAP[kind]
    with get_session() as session:
        channel = ChannelRepository.get_by_type(session, channel_type)
    text = messages.ask_channel(kind, channel.title if channel else None)
    context.user_data[KEY_PENDING_CHANNEL_KIND] = kind
    set_state(context.user_data, _STATE_MAP[kind])
    await update.callback_query.edit_message_text(text, reply_markup=keyboards.cancel_only())


async def handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kind = context.user_data.get(KEY_PENDING_CHANNEL_KIND)
    if kind not in _TYPE_MAP:
        return
    raw = update.message.text.strip()

    try:
        client = await ensure_started()
        if kind == "destination":
            info = await verify_destination_permissions(client, raw)
        else:
            info = await resolve_channel(client, raw)
    except ChannelAccessError as exc:
        if kind == "destination" and "Administrator" in str(exc):
            await update.message.reply_text(messages.PERMISSION_ERROR, reply_markup=keyboards.destination_retry())
        else:
            await update.message.reply_text(str(exc), reply_markup=keyboards.cancel_only())
        return
    except Exception:  # noqa: BLE001
        logger.exception("Channel resolution failed")
        await update.message.reply_text(messages.CHANNEL_NOT_FOUND, reply_markup=keyboards.cancel_only())
        return

    with get_session() as session:
        ChannelRepository.upsert(
            session,
            telegram_id=info.telegram_id,
            title=info.title,
            channel_type=_TYPE_MAP[kind],
            username=info.username,
        )

    text = messages.channel_confirmed(kind, info.title, info.telegram_id, info.username)
    prefix = "source" if kind == "source" else "destination"
    await update.message.reply_text(text, reply_markup=keyboards.channel_confirm(prefix))
    logger.info("%s channel configured: %s", kind, info.title)


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str) -> None:
    from app.handlers.dashboard import show_dashboard

    await update.callback_query.answer("✅ ذخیره شد")
    await show_dashboard(update, context, edit=False)


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
    await update.callback_query.edit_message_text(text, reply_markup=keyboards.channel_confirm("destination"))


async def handle_destination_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 راهنمای تنظیم کانال مقصد\n\n"
        "۱. ربات (یا حساب متصل) را به کانال مقصد اضافه کنید.\n"
        "۲. از بخش Administrators کانال، آن را Administrator کنید.\n"
        "۳. دسترسی «ارسال پیام» (Post Messages) را فعال کنید.\n"
        "۴. دوباره «بررسی مجدد» را بزنید."
    )
    await update.callback_query.edit_message_text(text, reply_markup=keyboards.destination_retry())
