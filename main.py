from __future__ import annotations

import asyncio
import logging
import logging.handlers
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import settings
from app.database.database import init_db
from app.telegram import auto_forward
from app.telegram.bot import build_application
from app.telegram.client import ensure_started, stop_client


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    log_format = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(log_format))
    root.addHandler(console)

    app_file = logging.handlers.RotatingFileHandler(
        "logs/app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    app_file.setFormatter(logging.Formatter(log_format))
    app_file.setLevel(logging.INFO)
    root.addHandler(app_file)

    error_file = logging.handlers.RotatingFileHandler(
        "logs/error.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    error_file.setFormatter(logging.Formatter(log_format))
    error_file.setLevel(logging.ERROR)
    root.addHandler(error_file)

    # جلوگیری از لاگ شدن کتابخانه‌های پرحجم در سطح DEBUG
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _post_init(application) -> None:  # noqa: ANN001
    client = await ensure_started()
    logging.getLogger(__name__).info("Telethon client متصل شد.")
    # اگر Auto-Forward قبلاً روشن بوده، دوباره فعالش کن (فقط پیام‌های از این لحظه به بعد)
    await auto_forward.sync_on_startup(client)


async def _post_shutdown(application) -> None:  # noqa: ANN001
    await stop_client()


def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting bot")

    init_db()

    application = build_application()
    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
