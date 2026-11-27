from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

from telegram.error import InvalidToken, NetworkError

from app.config import settings
from app.database.database import init_db
from app.handlers.reviews import notify_pending
from app.logging_config import setup_logging
from app.services.cleanup_service import auto_cleanup_loop
from app.services.review_store import recover_interrupted
from app.status_logging import monitor_status
from app.telegram import auto_forward
from app.telegram.bot import build_application, setup_bot_ui
from app.telegram.client import ensure_started, stop_client


async def _post_init(application) -> None:
    await setup_bot_ui(application.bot)

    client = await ensure_started(application.bot)
    logging.getLogger(__name__).info("Bot client connected (%s).", settings.platform)
    await auto_forward.sync_on_startup(client)
    application.bot_data["status_monitor"] = asyncio.create_task(monitor_status(client))
    application.bot_data["review_notifications"] = asyncio.create_task(
        notify_pending(application.bot)
    )
    if settings.db_auto_cleanup_enabled:
        application.bot_data["db_auto_cleanup"] = asyncio.create_task(
            auto_cleanup_loop(
                interval_hours=settings.db_cleanup_interval_hours,
                retention_days=settings.db_retention_days,
            )
        )


async def _post_shutdown(application) -> None:
    for name in ("status_monitor", "review_notifications", "db_auto_cleanup"):
        task = application.bot_data.pop(name, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    await stop_client()
    logging.getLogger(__name__).info("Shutdown completed; client disconnected.")


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    platform_label = "Telegram"
    logger.info("Starting bot... (%s Forwarder + AI Guardrails)", platform_label)

    init_db()
    recover_interrupted()

    application = build_application()
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else asyncio.new_event_loop
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        asyncio.set_event_loop(runner.get_loop())
        try:
            logger.info("Startup: connecting to %s Bot API...", platform_label)
            application.run_polling(
                allowed_updates=["message", "channel_post", "edited_channel_post", "callback_query"],
                bootstrap_retries=3,
                close_loop=False,
            )
        except InvalidToken:
            logger.error("توکن ربات پذیرفته نشد؛ BOT_TOKEN را بررسی کنید.")
            return 1
        except NetworkError as exc:
            logger.error(
                "اتصال Bot API برقرار نشد (%s). وضعیت اینترنت و پروکسی تنظیم‌شده را بررسی کنید؛ "
                "اگر پروکسی محلی است، برنامهٔ پروکسی باید روشن و مسیر سرویس قابل دسترس باشد.",
                type(exc).__name__,
            )
            return 1
        finally:
            asyncio.set_event_loop(None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
