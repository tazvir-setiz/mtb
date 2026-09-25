import logging

from telegram import Bot, BotCommand, MenuButtonCommands
from telegram.error import TelegramError

from app.ui import messages

logger = logging.getLogger(__name__)


async def setup_bot_ui(bot: Bot) -> None:
    commands = [
        BotCommand("start", "شروع و تنظیم کانال‌ها"),
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
