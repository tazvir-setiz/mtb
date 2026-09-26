import logging
import logging.handlers
import sys
import time
from pathlib import Path

from app.config import settings
from app.log_context import ContextFilter


def setup_logging() -> None:
    log_format = "%(asctime)s UTC | %(levelname)-8s | %(name)s:%(lineno)d | %(trace)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    formatter.converter = time.gmtime

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    for handler in root.handlers[:]:
        if getattr(handler, "forwarder_handler", False):
            root.removeHandler(handler)
            handler.close()

    def attach(handler):
        handler.forwarder_handler = True
        handler.addFilter(ContextFilter())
        handler.setFormatter(formatter)
        root.addHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    attach(console)

    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    if not settings.log_to_file:
        return

    Path("logs").mkdir(exist_ok=True)

    app_file = logging.handlers.RotatingFileHandler(
        "logs/app.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    attach(app_file)

    error_file = logging.handlers.RotatingFileHandler(
        "logs/error.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    error_file.setLevel(logging.WARNING)
    attach(error_file)
