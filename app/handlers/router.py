from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers import settings as settings_handlers
from app.handlers import source, transfer
from app.handlers.auth import is_authorized, reject
from app.handlers.callback_routes import CALLBACK_ROUTES
from app.handlers.states import State, get_state
from app.ui import keyboards
from app.ui.callbacks import parse

logger = logging.getLogger(__name__)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    if not is_authorized(update):
        await reject(update)
        return

    # Callback را سریع ACK می‌کنیم تا spinner تلگرام باقی نماند.
    await query.answer()
    namespace, action, _arg = parse(query.data or "")

    try:
        handler = CALLBACK_ROUTES.get((namespace, action))
        if handler:
            await handler(update, context)

    except Exception:  # noqa: BLE001
        logger.exception("خطا در پردازش callback: %s", query.data)
        if update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطای غیرمنتظره‌ای رخ داد.\nاز /menu برای بازگشت به داشبورد استفاده کنید."
            )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    state = get_state(context.user_data)
    try:
        if state in (State.SOURCE_CHANNEL, State.DESTINATION_CHANNEL):
            await source.handle_channel_input(update, context)
        elif state in (State.RANGE_INPUT_START, State.RANGE_INPUT_END, State.IDS_INPUT):
            await transfer.handle_text_input(update, context, state)
        elif state == State.SIGNATURE_INPUT:
            await settings_handlers.handle_signature_input(update, context)
        else:
            await update.message.reply_text(
                "از دکمه‌های داشبورد استفاده کنید یا /menu را بزنید.",
                reply_markup=keyboards.back_home(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("خطا در پردازش ورودی متنی")
        await update.message.reply_text("⚠️ خطای غیرمنتظره‌ای رخ داد.\nبرای بازگشت /menu را بزنید.")
