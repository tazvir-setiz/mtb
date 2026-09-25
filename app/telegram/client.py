from __future__ import annotations

import logging
import os
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import ConfigError, settings
from app.telegram.session import create_session

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def _get_proxy() -> tuple | None:
    if os.getenv("PROXY_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return None

    try:
        import socks
    except ImportError:
        logger.error("PROXY_ENABLED=true است اما پکیج PySocks نصب نیست. دستور: pip install PySocks")
        raise

    proxy_type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }
    proxy_type_name = os.getenv("PROXY_TYPE", "socks5").lower()
    proxy_type = proxy_type_map.get(proxy_type_name, socks.SOCKS5)

    host = os.getenv("PROXY_HOST", "127.0.0.1")
    port = int(os.getenv("PROXY_PORT", "12334"))
    username = os.getenv("PROXY_USERNAME") or None
    password = os.getenv("PROXY_PASSWORD") or None

    if username and password:
        proxy = (proxy_type, host, port, True, username, password)
    else:
        proxy = (proxy_type, host, port)

    logger.info("اتصال Telethon از طریق پروکسی %s://%s:%s", proxy_type_name, host, port)
    return proxy


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        _client = TelegramClient(
            create_session(settings.telethon_session, settings.telethon_string_session),
            settings.api_id,
            settings.api_hash,
            proxy=_get_proxy(),
        )
    return _client


async def ensure_started() -> TelegramClient:
    client = get_client()
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        if not sys.stdin or not sys.stdin.isatty():
            await client.disconnect()
            raise ConfigError(
                "Telethon session is not authorized and interactive login is unavailable. "
                "Generate TELETHON_STRING_SESSION locally with python -m scripts.export_session "
                "and set it in Railway Variables before deploying. "
                "If a revoked session already exists on the volume, replace that session file."
            )
        logger.warning("Telethon session احراز هویت نشده است؛ ورود تعاملی آغاز می‌شود.")
        try:
            await client.start()  # type: ignore[func-returns-value]
        except SessionPasswordNeededError:
            logger.error("حساب دارای Two-Step Verification است؛ رمز عبور را وارد کنید.")
            raise
    if settings.telethon_string_session:
        # StringSession contains credentials, but not channel access hashes.
        # Populate the persistent entity cache for channels configured by numeric ID.
        await client.get_dialogs()
    return client


async def stop_client() -> None:
    global _client
    if _client is not None and _client.is_connected():
        await _client.disconnect()
