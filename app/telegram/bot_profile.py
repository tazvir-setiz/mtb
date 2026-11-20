"""Publish the bot's command menu and profile text.

Bale's Bot API implements only part of Telegram's surface and answers unknown methods with
``InvalidToken: Handler not found`` (Telegram added the menu-button and description methods in
Bot API 6.0, which Bale does not expose).  Each step is therefore applied on its own: an
unsupported method is reported once at INFO level and the remaining steps still run, instead of
aborting profile setup with a traceback on every startup.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from telegram import Bot, BotCommand, MenuButtonCommands
from telegram.error import TelegramError

from app.config import settings
from app.ui import messages

logger = logging.getLogger(__name__)


async def setup_bot_ui(bot: Bot) -> None:
    commands = [
        BotCommand("start", "شروع و تنظیم کانال‌ها"),
        BotCommand("menu", "🏠 داشبورد اصلی"),
        BotCommand("stats", "📊 آمار انتقال‌ها"),
        BotCommand("recent", "🕘 پیام‌های اخیر"),
        BotCommand("status", "🩺 تست سلامت سیستم"),
        BotCommand("reviews", "🔎 تصمیم‌گیری درباره پیام‌های متوقف‌شده"),
        BotCommand("settings", "⚙️ تنظیمات"),
        BotCommand("help", "❓ راهنما"),
        BotCommand("cancel", "✕ لغو جریان فعلی"),
    ]

    steps: tuple[tuple[str, Callable[[], Awaitable[object]]], ...] = (
        ("command menu", lambda: bot.set_my_commands(commands)),
        ("chat menu button", lambda: bot.set_chat_menu_button(menu_button=MenuButtonCommands())),
        (
            "short description",
            lambda: bot.set_my_short_description(messages.BOT_SHORT_DESCRIPTION),
        ),
        ("description", lambda: bot.set_my_description(messages.BOT_DESCRIPTION)),
    )

    applied: list[str] = []
    for label, apply_step in steps:
        try:
            await apply_step()
        except TelegramError as exc:
            logger.info(
                "Bot %s not applied on %s (%s: %s); continuing.",
                label,
                settings.platform,
                type(exc).__name__,
                exc,
            )
        else:
            applied.append(label)

    if applied:
        logger.info("Bot profile configured: %s.", ", ".join(applied))
    else:
        logger.warning(
            "No bot profile step was accepted by %s; check BOT_TOKEN and PLATFORM.",
            settings.platform,
        )
