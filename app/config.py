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
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1]

    ids: list[int] = []
    for part in raw.split(","):
        cleaned = part.strip().strip("[]").strip().strip("'\"").strip()
        if not cleaned:
            continue
        try:
            ids.append(int(cleaned))
        except ValueError:
            continue

    return ids


@dataclass(frozen=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    admin_ids: list[int] = field(default_factory=list)
    database_url: str = "sqlite:///data/forwarder.db"
    telethon_session: str = "sessions/forwarder_session"
    telethon_string_session: str = field(default="", repr=False)
    log_level: str = "INFO"
    log_to_file: bool = True
    forward_delay: float = 1.5
    progress_update_interval: float = 3.0

    # تنظیمات AI
    ai_enabled: bool = False
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1/chat/completions"
    ai_model: str = "gpt-4o-mini"
    ai_guardrails: str = ""

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def load_settings() -> Settings:
    bot_token = _get_env("BOT_TOKEN")
    api_id = int(_get_env("API_ID"))
    api_hash = _get_env("API_HASH")
    admin_ids = _parse_admin_ids(_get_env("ADMIN_IDS", required=False, default=""))
    database_url = _get_env("DATABASE_URL", required=False, default="sqlite:///data/forwarder.db")
    telethon_session = _get_env(
        "TELETHON_SESSION", required=False, default="sessions/forwarder_session"
    )
    log_level = _get_env("LOG_LEVEL", required=False, default="INFO")
    telethon_string_session = _get_env(
        "TELETHON_STRING_SESSION", required=False, default=""
    ).strip()
    log_to_file = _get_env("LOG_TO_FILE", required=False, default="true").lower() in (
        "1",
        "true",
        "yes",
    )
    forward_delay = float(_get_env("FORWARD_DELAY", required=False, default="1.5"))
    progress_interval = float(_get_env("PROGRESS_UPDATE_INTERVAL", required=False, default="3"))

    # AI Envs
    ai_enabled = _get_env("AI_ENABLED", required=False, default="false").lower() in (
        "1",
        "true",
        "yes",
    )
    ai_api_key = _get_env("AI_API_KEY", required=False, default="")
    ai_base_url = _get_env(
        "AI_BASE_URL", required=False, default="https://api.openai.com/v1/chat/completions"
    )
    ai_model = _get_env("AI_MODEL", required=False, default="gpt-4o-mini")
    ai_guardrails = _get_env("AI_GUARDRAILS", required=False, default="")
    if not ai_guardrails.strip():
        ai_guardrails = (BASE_DIR / "app/prompts/guardrails.txt").read_text(encoding="utf-8")

    return Settings(
        bot_token=bot_token,
        api_id=api_id,
        api_hash=api_hash,
        admin_ids=admin_ids,
        database_url=database_url,
        telethon_session=telethon_session,
        telethon_string_session=telethon_string_session,
        log_level=log_level,
        log_to_file=log_to_file,
        forward_delay=forward_delay,
        progress_update_interval=progress_interval,
        ai_enabled=ai_enabled,
        ai_api_key=ai_api_key,
        ai_base_url=ai_base_url,
        ai_model=ai_model,
        ai_guardrails=ai_guardrails,
    )


settings = load_settings()
