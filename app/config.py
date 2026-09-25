from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

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

    ai_enabled: bool = False
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1/chat/completions"
    ai_model: str = "gpt-4o-mini"
    ai_guardrails: str = ""

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


def optional_env(name: str, default: str = "") -> str:
    return _get_env(name, required=False, default=default)


def env_flag(name: str, default: str = "false") -> bool:
    return optional_env(name, default).lower() in ("1", "true", "yes")


def load_guardrails() -> str:
    custom = optional_env("AI_GUARDRAILS")
    return (
        custom
        if custom.strip()
        else (BASE_DIR / "app/prompts/guardrails.txt").read_text(encoding="utf-8")
    )


def load_settings() -> Settings:
    return Settings(
        bot_token=_get_env("BOT_TOKEN"),
        api_id=int(_get_env("API_ID")),
        api_hash=_get_env("API_HASH"),
        admin_ids=_parse_admin_ids(optional_env("ADMIN_IDS")),
        database_url=optional_env("DATABASE_URL", "sqlite:///data/forwarder.db"),
        telethon_session=optional_env("TELETHON_SESSION", "sessions/forwarder_session"),
        telethon_string_session=optional_env("TELETHON_STRING_SESSION").strip(),
        log_level=optional_env("LOG_LEVEL", "INFO"),
        log_to_file=env_flag("LOG_TO_FILE", "true"),
        forward_delay=float(optional_env("FORWARD_DELAY", "1.5")),
        progress_update_interval=float(optional_env("PROGRESS_UPDATE_INTERVAL", "3")),
        ai_enabled=env_flag("AI_ENABLED"),
        ai_api_key=optional_env("AI_API_KEY"),
        ai_base_url=optional_env("AI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
        ai_model=optional_env("AI_MODEL", "gpt-4o-mini"),
        ai_guardrails=load_guardrails(),
    )


settings = load_settings()
