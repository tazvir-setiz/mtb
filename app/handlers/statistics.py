from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.services.statistics_service import (
    clear_statistics,
    get_recent_messages,
    get_statistics_text,
)
from app.ui import keyboards, messages


async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = get_statistics_text()
    await update.callback_query.edit_message_text(
        text,
        reply_markup=keyboards.stats_menu(),
    )


async def refresh_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("آمار به‌روز شد")
    await show_statistics(update, context)


async def ask_clear_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text(
        messages.clear_statistics_confirm_text(),
        reply_markup=keyboards.confirm_clear_statistics(),
    )


async def clear_statistics_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    clear_statistics()
    await update.callback_query.answer("آمار پاک شد")
    await show_statistics(update, context)


async def show_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = get_recent_messages()
    await update.callback_query.edit_message_text(
        messages.recent_messages_text(items),
        reply_markup=keyboards.back_home(),
    )
