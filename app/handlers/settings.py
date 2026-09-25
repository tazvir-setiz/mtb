from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.ui import keyboards, messages


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        signature = SettingsRepository.get(session, "signature_text")
    text = messages.settings_text(signature)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboards.settings_menu())
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboards.settings_menu())


async def ask_signature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.handlers.states import State, set_state
    set_state(context.user_data, State.SIGNATURE_INPUT)
    await update.callback_query.edit_message_text(
        messages.ask_signature(), reply_markup=keyboards.signature_menu()
    )


async def clear_signature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        SettingsRepository.set(session, "signature_text", "")
    await update.callback_query.answer("🗑 امضا حذف شد.", show_alert=True)
    await show_settings(update, context)


async def show_delay_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer(
        f"فاصله فعلی بین هر Forward: {settings.forward_delay} ثانیه (از .env قابل تغییر است).",
        show_alert=True,
    )


async def clear_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        SettingsRepository.clear_all_data(session)
    await update.callback_query.answer("🧹 داده‌های عملیات پاک شد.", show_alert=True)
    await show_settings(update, context)


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.ui.messages import HELP_TEXT

    await update.callback_query.edit_message_text(HELP_TEXT, reply_markup=keyboards.back_home())