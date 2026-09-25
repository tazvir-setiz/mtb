from telegram import Update
from telegram.ext import ContextTypes

from app.handlers import dashboard
from app.handlers import settings as settings_handlers
from app.handlers.auth import is_authorized, reject
from app.handlers.states import reset
from app.ui import keyboards, messages


async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    from app.services.statistics_service import get_statistics_text

    await update.effective_message.reply_text(
        get_statistics_text(),
        reply_markup=keyboards.stats_menu(),
    )


async def command_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    from app.services.statistics_service import get_recent_messages

    await update.effective_message.reply_text(
        messages.recent_messages_text(get_recent_messages()),
        reply_markup=keyboards.back_home(),
    )


async def command_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    await settings_handlers.show_settings(update, context)


async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    await update.effective_message.reply_text(
        messages.HELP_TEXT,
        reply_markup=keyboards.back_home(),
    )


async def command_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update):
        await reject(update)
        return

    reset(context.user_data)
    await dashboard.show_dashboard(update, context)
