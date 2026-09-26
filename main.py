from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database.database import init_db
from app.handlers.reviews import notify_pending
from app.logging_config import setup_logging
from app.services.review_store import recover_interrupted
from app.status_logging import monitor_status
from app.telegram import auto_forward
from app.telegram.bot import build_application, setup_bot_ui
from app.telegram.client import ensure_started, stop_client


async def _post_init(application) -> None:
    await setup_bot_ui(application.bot)

    client = await ensure_started()
    logging.getLogger(__name__).info("Telethon client متصل شد.")
    await auto_forward.sync_on_startup(client)
    application.bot_data["status_monitor"] = asyncio.create_task(monitor_status(client))
    application.bot_data["review_notifications"] = asyncio.create_task(
        notify_pending(application.bot)
    )


async def _post_shutdown(application) -> None:
    for name in ("status_monitor", "review_notifications"):
        task = application.bot_data.pop(name, None)
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    await stop_client()
    logging.getLogger(__name__).info("Shutdown completed; Telegram client disconnected.")


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot... (Telegram Forwarder + AI Guardrails)")

    init_db()
    recover_interrupted()

    application = build_application()
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
