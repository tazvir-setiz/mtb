from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    Defaults,
    MessageHandler,
    filters,
)

from app.config import settings
from app.handlers import guard_settings, reviews, source, start
from app.handlers.commands import (
    command_cancel,
    command_health,
    command_help,
    command_recent,
    command_settings,
    command_stats,
)
from app.handlers.router import on_callback, on_text
from app.telegram import auto_forward, seen_chats
from app.telegram.bot_profile import setup_bot_ui as setup_bot_ui
from app.telegram.bot_proxy import get_bot_api_proxy_url
from app.telegram.client import set_bot


async def _remember_bot_membership(update, context) -> None:
    """Record the chat when the bot itself is added to a channel/group.

    Bale sends ``my_chat_member`` when a bot is added to a channel; that update carries
    the channel object (and therefore its id) even though ``getChat`` cannot resolve it.
    """
    member_update = getattr(update, "my_chat_member", None)
    if member_update is None:
        return
    seen_chats.record(getattr(member_update, "chat", None))


def build_application() -> Application:
    defaults = Defaults(parse_mode=ParseMode.HTML)

    builder = (
        Application.builder()
        .token(settings.bot_token)
        .defaults(defaults)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
    )
    proxy_url = get_bot_api_proxy_url()
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

    application = builder.build()
    set_bot(application.bot)

    application.add_handler(CommandHandler("start", start.handle_start))
    application.add_handler(CommandHandler("menu", start.handle_start))
    application.add_handler(CommandHandler("stats", command_stats))
    application.add_handler(CommandHandler("recent", command_recent))
    application.add_handler(CommandHandler("health", command_health))
    application.add_handler(CommandHandler("status", command_health))
    application.add_handler(CommandHandler("settings", command_settings))
    application.add_handler(CommandHandler("help", command_help))
    application.add_handler(CommandHandler("cancel", command_cancel))

    application.add_handler(CommandHandler("reviews", reviews.show_pending))
    application.add_handler(CallbackQueryHandler(reviews.on_callback, pattern=r"^review:"))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.StatusUpdate.CHAT_SHARED, source.handle_chat_shared))
    application.add_handler(MessageHandler(filters.FORWARDED & ~filters.COMMAND & ~filters.TEXT, source.handle_forwarded_channel))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(MessageHandler(filters.Document.ALL, guard_settings.receive))

    # Channel post listener in separate handler group to avoid interfering with command/menu handlers
    channel_post_filter = (
        filters.ChatType.CHANNEL | filters.ChatType.GROUPS | filters.UpdateType.CHANNEL_POST
    ) & ~filters.COMMAND
    application.add_handler(MessageHandler(channel_post_filter, auto_forward.handle_channel_update), group=1)

    # Remember channels the bot is added to (Bale only exposes the id via this update).
    application.add_handler(
        ChatMemberHandler(
            _remember_bot_membership, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER
        ),
        group=2,
    )

    async def _on_error(update, context):
        import logging

        from telegram.error import NetworkError, TimedOut

        logger = logging.getLogger(__name__)
        if isinstance(context.error, (TimedOut, NetworkError)):
            logger.warning("Telegram network timeout/error: %s", context.error)
        else:
            logger.exception("Unhandled telegram exception: %s", context.error)

    application.add_error_handler(_on_error)

    return application
