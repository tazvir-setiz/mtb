import logging
import logging.handlers
import sys
from pathlib import Path

from app.config import settings


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(filename)s:%(lineno)d | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    app_file = logging.handlers.RotatingFileHandler(
        "logs/app.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    app_file.setFormatter(formatter)
    app_file.setLevel(logging.INFO)
    root.addHandler(app_file)

    error_file = logging.handlers.RotatingFileHandler(
        "logs/error.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    error_file.setFormatter(formatter)
    error_file.setLevel(logging.ERROR)
    root.addHandler(error_file)

    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
