"""
Telethon (MTProto) client.

چرا Telethon؟
Bot API نمی‌تواند تاریخچه پیام‌های قدیمی یک کانال را بخواند و نمی‌تواند
پیام را با Message ID دلخواه از یک کانال دریافت کند (فقط پیام‌هایی که مستقیم
برای بات ارسال/فوروارد شده‌اند در دسترس بات هستند). به همین دلیل عملیات
خواندن و Forward واقعی پیام‌های کانال با یک حساب کاربری واقعی (User Account)
از طریق Telethon انجام می‌شود. این حساب باید عضو کانال مبدأ و عضو/ادمین
کانال مقصد باشد.

پنل مدیریت (Dashboard, Inline Keyboard) با Bot API (python-telegram-bot)
پیاده‌سازی شده و صرفاً واسط کاربری ادمین است؛ عملیات واقعی Telegram توسط
همین کلاینت Telethon انجام می‌شود.
"""
from __future__ import annotations

import logging
import os

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def _get_proxy() -> tuple | None:
    """
    تنظیمات پروکسی را از .env می‌خواند (اختیاری).

    اگر اینترنت مستقیماً به سرورهای Telegram دسترسی نداشته باشد (فیلترینگ)،
    باید یک پروکسی محلی (مثلاً Hiddify, v2rayN, Nekoray) تعریف شود.

    متغیرهای .env:
        PROXY_ENABLED=true
        PROXY_TYPE=socks5      # socks5 | socks4 | http
        PROXY_HOST=127.0.0.1
        PROXY_PORT=12334
        PROXY_USERNAME=        # اختیاری
        PROXY_PASSWORD=        # اختیاری
    """
    if os.getenv("PROXY_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return None

    try:
        import socks
    except ImportError:
        logger.error(
            "PROXY_ENABLED=true است اما پکیج PySocks نصب نیست. "
            "دستور: pip install PySocks"
        )
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
            settings.telethon_session,
            settings.api_id,
            settings.api_hash,
            proxy=_get_proxy(),
        )
    return _client


async def ensure_started() -> TelegramClient:
    """
    اتصال کلاینت Telethon را برقرار می‌کند.
    اگر session از قبل Login نشده باشد، اجرای این تابع در حالت تعاملی
    (اولین اجرا) شماره تلفن/کد/رمز دو مرحله‌ای را از طریق کنسول درخواست می‌کند.
    برای جزئیات به README بخش «اولین Login به Telethon» مراجعه کنید.
    """
    client = get_client()
    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        logger.warning("Telethon session احراز هویت نشده است؛ ورود تعاملی آغاز می‌شود.")
        try:
            await client.start()  # type: ignore[func-returns-value]
        except SessionPasswordNeededError:
            logger.error("حساب دارای Two-Step Verification است؛ رمز عبور را وارد کنید.")
            raise
    return client


async def stop_client() -> None:
    global _client
    if _client is not None and _client.is_connected():
        await _client.disconnect()