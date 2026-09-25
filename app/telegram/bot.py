from __future__ import annotations

import logging
import os

from telegram import Bot, BotCommand, MenuButtonCommands, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

from app.config import settings
from app.handlers import (
    dashboard,
    destination,
    settings as settings_handlers,
    source,
    start,
    statistics,
    transfer,
)
from app.handlers.states import State, get_state, reset
from app.ui import keyboards, messages
from app.ui.callbacks import parse

logger = logging.getLogger(__name__)


def _is_authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and settings.is_admin(user.id)


async def _reject(update: Update) -> None:
    if update.callback_query:
        await update.callback_query.answer(messages.UNAUTHORIZED, show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(messages.UNAUTHORIZED)


async def setup_bot_ui(bot: Bot) -> None:
    """تنظیم Command Menu و توضیحات پروفایل ربات در Telegram."""
    commands = [
        BotCommand("menu", "🏠 داشبورد اصلی"),
        BotCommand("stats", "📊 آمار انتقال‌ها"),
        BotCommand("recent", "🕘 پیام‌های اخیر"),
        BotCommand("settings", "⚙️ تنظیمات"),
        BotCommand("help", "❓ راهنما"),
        BotCommand("cancel", "✕ لغو جریان فعلی"),
    ]

    try:
        await bot.set_my_commands(commands)
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        await bot.set_my_short_description(messages.BOT_SHORT_DESCRIPTION)
        await bot.set_my_description(messages.BOT_DESCRIPTION)
        logger.info("Telegram command menu/profile UI configured.")
    except TelegramError:
        logger.exception("Could not configure Telegram command menu/profile UI.")


async def command_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    from app.services.statistics_service import get_statistics_text

    await update.effective_message.reply_text(
        get_statistics_text(),
        reply_markup=keyboards.stats_menu(),
    )


async def command_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    from app.services.statistics_service import get_recent_messages

    await update.effective_message.reply_text(
        messages.recent_messages_text(get_recent_messages()),
        reply_markup=keyboards.back_home(),
    )


async def command_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    await settings_handlers.show_settings(update, context)


async def command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    await update.effective_message.reply_text(
        messages.HELP_TEXT,
        reply_markup=keyboards.back_home(),
    )


async def command_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    reset(context.user_data)
    await dashboard.show_dashboard(update, context)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    if not _is_authorized(update):
        await _reject(update)
        return

    # Callback را سریع ACK می‌کنیم تا spinner تلگرام باقی نماند.
    await query.answer()
    namespace, action, arg = parse(query.data or "")

    try:
        if namespace == "menu":
            if action == "source":
                await source.show_channel_prompt(update, context, "source")
            elif action == "destination":
                await source.show_channel_prompt(update, context, "destination")
            elif action == "transfer":
                await transfer.show_transfer_menu(update, context)
            elif action == "recent":
                await statistics.show_recent(update, context)
            elif action == "stats":
                await statistics.show_statistics(update, context)
            elif action == "settings":
                await settings_handlers.show_settings(update, context)
            elif action == "help":
                await settings_handlers.show_help(update, context)
            elif action == "auto_toggle":
                await dashboard.toggle_auto_forward(update, context)
            return

        if namespace == "nav":
            if action in ("home", "cancel", "back"):
                await dashboard.show_dashboard(update, context, edit=True)
            return

        if namespace == "source":
            if action == "confirm":
                await source.handle_confirm(update, context, "source")
            elif action == "change":
                await source.handle_change(update, context, "source")
            return

        if namespace == "destination":
            if action == "confirm":
                await source.handle_confirm(update, context, "destination")
            elif action == "change":
                await source.handle_change(update, context, "destination")
            elif action == "retry":
                await destination.handle_destination_retry(update, context)
            elif action == "help":
                await destination.handle_destination_help(update, context)
            return

        if namespace == "transfer":
            if action == "range":
                await transfer.start_range_flow(update, context)
            elif action == "ids":
                await transfer.start_ids_flow(update, context)
            elif action == "new":
                await transfer.start_new_messages_flow(update, context)
            elif action == "edit":
                await transfer.edit_range(update, context)
            elif action == "confirm":
                await transfer.confirm_and_start(update, context)
            elif action == "pause":
                await transfer.pause_transfer(update, context)
            elif action == "resume":
                await transfer.resume_transfer(update, context)
            elif action == "restart":
                await transfer.show_transfer_menu(update, context)
            elif action == "errors":
                await transfer.show_errors(update, context)
            elif action == "retry":
                await transfer.retry_failed_messages(update, context)
            elif action == "start":
                await transfer.show_confirm_from_range(update, context)
            return

        if namespace == "stats":
            if action == "refresh":
                await statistics.refresh_statistics(update, context)
            elif action == "clear":
                await statistics.ask_clear_statistics(update, context)
            elif action == "clear_confirm":
                await statistics.clear_statistics_handler(update, context)
            return

        if namespace == "settings":
            if action == "delay":
                await settings_handlers.show_delay_info(update, context)
            elif action == "clear_data":
                await settings_handlers.ask_clear_data(update, context)
            elif action == "clear_data_confirm":
                await settings_handlers.clear_data(update, context)
            elif action == "signature":
                await settings_handlers.ask_signature(update, context)
            elif action == "clear_sig":
                await settings_handlers.clear_signature(update, context)
            return

    except Exception:  # noqa: BLE001
        logger.exception("خطا در پردازش callback: %s", query.data)
        if update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ خطای غیرمنتظره‌ای رخ داد.\nاز /menu برای بازگشت به داشبورد استفاده کنید."
            )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _reject(update)
        return

    state = get_state(context.user_data)
    try:
        if state in (State.SOURCE_CHANNEL, State.DESTINATION_CHANNEL):
            await source.handle_channel_input(update, context)
        elif state in (State.RANGE_INPUT_START, State.RANGE_INPUT_END, State.IDS_INPUT):
            await transfer.handle_text_input(update, context, state)
        elif state == State.SIGNATURE_INPUT:
            from app.database.database import get_session
            from app.database.repository import SettingsRepository

            text_html = update.message.text_html
            with get_session() as session:
                SettingsRepository.set(session, "signature_text", text_html)

            await update.message.reply_text("✅ امضا ذخیره شد.")
            reset(context.user_data)
            await settings_handlers.show_settings(update, context)
        else:
            await update.message.reply_text(
                "از دکمه‌های داشبورد استفاده کنید یا /menu را بزنید.",
                reply_markup=keyboards.back_home(),
            )
    except Exception:  # noqa: BLE001
        logger.exception("خطا در پردازش ورودی متنی")
        await update.message.reply_text(
            "⚠️ خطای غیرمنتظره‌ای رخ داد.\nبرای بازگشت /menu را بزنید."
        )


def _get_bot_api_proxy_url() -> str | None:
    if os.getenv("PROXY_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return None

    scheme_map = {
        "socks5": "socks5h",
        "socks4": "socks4",
        "http": "http",
    }
    proxy_type_name = os.getenv("PROXY_TYPE", "socks5").lower()
    scheme = scheme_map.get(proxy_type_name, "socks5h")

    host = os.getenv("PROXY_HOST", "127.0.0.1")
    port = os.getenv("PROXY_PORT", "12334")
    username = os.getenv("PROXY_USERNAME") or None
    password = os.getenv("PROXY_PASSWORD") or None

    if username and password:
        url = f"{scheme}://{username}:{password}@{host}:{port}"
    else:
        url = f"{scheme}://{host}:{port}"

    logger.info(
        "اتصال Bot API (python-telegram-bot) از طریق پروکسی %s://%s:%s",
        proxy_type_name,
        host,
        port,
    )
    return url


def build_application() -> Application:
    builder = (
        Application.builder()
        .token(settings.bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
    )

    proxy_url = _get_bot_api_proxy_url()
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

    application = builder.build()

    application.add_handler(CommandHandler("start", start.handle_start))
    application.add_handler(CommandHandler("menu", start.handle_start))
    application.add_handler(CommandHandler("stats", command_stats))
    application.add_handler(CommandHandler("recent", command_recent))
    application.add_handler(CommandHandler("settings", command_settings))
    application.add_handler(CommandHandler("help", command_help))
    application.add_handler(CommandHandler("cancel", command_cancel))

    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return application
