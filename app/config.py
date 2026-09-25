"""
Configuration loader.
تمام مقادیر حساس فقط از .env خوانده می‌شوند و هرگز داخل کد قرار نمی‌گیرند.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """خطا در بارگذاری تنظیمات."""


def _get_env(name: str, required: bool = True, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ConfigError(f"متغیر محیطی الزامی یافت نشد: {name}")
    return value or ""


def _parse_admin_ids(raw: str) -> list[int]:
    """
    ADMIN_IDS را به‌صورت مقاوم پارس می‌کند.

    برخلاف کتابخانه‌هایی مثل pydantic-settings که برای فیلدهای لیستی انتظار
    JSON خالص دارند (مثلاً ``["123456789"]``)، این تابع همه فرمت‌های زیر را
    که معمولاً در پنل‌های Deploy (مثل Railway/Docker/systemd) تایپ می‌شوند
    می‌پذیرد و اگر یک آیتم قابل تبدیل به عدد نبود، فقط همان آیتم را نادیده
    می‌گیرد (نه کل مقدار را):

        123456789
        123456789,987654321
        123456789, 987654321   (با فاصله)
        [123456789, 987654321] (JSON-style)
        ["123456789", "987654321"] (JSON-style با رشته)
        "123456789"             (با کوتیشن دور کل مقدار)
    """
    raw = raw.strip()
    if not raw:
        return []

    # حذف کروشه یا کوتیشن دورِ کل مقدار (فرمت JSON یا کوتیشن‌دار)
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1]

    ids: list[int] = []
    for part in raw.split(","):
        # کوتیشن، فاصله و براکت احتمالی دورِ هر آیتم را جدا حذف می‌کند
        cleaned = part.strip().strip("[]").strip().strip("'\"").strip()
        if not cleaned:
            continue
        try:
            ids.append(int(cleaned))
        except ValueError:
            logger.warning("مقدار ADMIN_IDS نامعتبر و نادیده گرفته شد: %r", part)
            continue

    if not ids:
        logger.warning(
            "ADMIN_IDS is empty - no one will be able to use this bot's dashboard."
        )
    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    admin_ids: list[int] = field(default_factory=list)
    database_url: str = "sqlite:///data/forwarder.db"
    telethon_session: str = "sessions/forwarder_session"
    log_level: str = "INFO"
    forward_delay: float = 1.5
    progress_update_interval: float = 3.0

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_settings() -> Settings:
    bot_token = _get_env("BOT_TOKEN")
    api_id_raw = _get_env("API_ID")
    api_hash = _get_env("API_HASH")
    admin_ids_raw = _get_env("ADMIN_IDS", required=False, default="")

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise ConfigError("API_ID باید عددی باشد") from exc

    database_url = _get_env("DATABASE_URL", required=False, default="sqlite:///data/forwarder.db")
    telethon_session = _get_env(
        "TELETHON_SESSION", required=False, default="sessions/forwarder_session"
    )
    log_level = _get_env("LOG_LEVEL", required=False, default="INFO")

    forward_delay_raw = _get_env("FORWARD_DELAY", required=False, default="1.5")
    progress_interval_raw = _get_env("PROGRESS_UPDATE_INTERVAL", required=False, default="3")

    return Settings(
        bot_token=bot_token,
        api_id=api_id,
        api_hash=api_hash,
        admin_ids=_parse_admin_ids(admin_ids_raw),
        database_url=database_url,
        telethon_session=telethon_session,
        log_level=log_level,
        forward_delay=float(forward_delay_raw),
        progress_update_interval=float(progress_interval_raw),
    )


settings = load_settings()
