from __future__ import annotations

import asyncio
import logging
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database.database import init_db
from app.logging_config import setup_logging
from app.telegram import auto_forward
from app.telegram.bot import build_application, setup_bot_ui
from app.telegram.client import ensure_started, stop_client


async def _post_init(application) -> None:  # noqa: ANN001
    await setup_bot_ui(application.bot)

    client = await ensure_started()
    logging.getLogger(__name__).info("Telethon client متصل شد.")
    await auto_forward.sync_on_startup(client)


async def _post_shutdown(application) -> None:  # noqa: ANN001
    await stop_client()


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot... (Telegram Forwarder + AI Guardrails)")

    init_db()

    application = build_application()
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
