from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    Defaults,
    MessageHandler,
    filters,
)

from app.config import settings
from app.handlers import start
from app.handlers.commands import (
    command_cancel,
    command_help,
    command_recent,
    command_settings,
    command_stats,
)
from app.handlers.router import on_callback, on_text
from app.telegram.bot_profile import setup_bot_ui as setup_bot_ui
from app.telegram.bot_proxy import get_bot_api_proxy_url


def build_application() -> Application:
    builder = (
        Application.builder()
        .token(settings.bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
    )

    proxy_url = get_bot_api_proxy_url()
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
