from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.config import Settings, settings
from app.database.database import get_session
from app.database.repository import SettingsRepository


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    api_key: str = field(repr=False)
    base_url: str
    model: str


def load_ai_settings(defaults: Settings = settings) -> AISettings:
    with get_session() as session:

        def read(name: str, fallback: str) -> str:
            return SettingsRepository.get(session, f"ai_{name}", default=fallback)

        return AISettings(
            enabled=read("enabled", "true" if defaults.ai_enabled else "false") == "true",
            api_key=read("api_key", defaults.ai_api_key),
            base_url=read("base_url", defaults.ai_base_url),
            model=read("model", defaults.ai_model),
        )


def validate_ai_value(name: str, value: str) -> str | None:
    if not value or any(char.isspace() for char in value):
        return "مقدار نباید خالی یا دارای فاصله باشد."
    if name == "base_url":
        try:
            url = urlsplit(value)
            valid = (
                url.scheme == "https"
                and url.hostname
                and not (url.username or url.password or url.query or url.fragment)
            )
            url.port
        except ValueError:
            valid = False
        if not valid or len(value) > 2048:
            return "آدرس کامل HTTPS را بدون لینک مارک‌داون، رمز یا پارامتر اضافی بفرستید."
    elif name == "api_key":
        if len(value) > 4096 or value == "sk-your-api-key-here":
            return "کلید واقعی سرویس را وارد کنید؛ مقدار نمونه معتبر نیست."
    elif name == "model":
        if len(value) > 200 or any(ord(char) < 32 for char in value):
            return "نام مدل معتبر نیست."
    return None


def save_ai_value(name: str, value: str) -> None:
    if name not in {"enabled", "api_key", "base_url", "model"}:
        raise ValueError("Unknown AI setting")
    current = load_ai_settings()
    with get_session() as session:
        SettingsRepository.set(session, f"ai_{name}", value)
        if name == "base_url" and value != current.base_url:
            SettingsRepository.set(session, "ai_api_key", "")
            SettingsRepository.set(session, "ai_enabled", "false")
        if name == "api_key" and not value:
            SettingsRepository.set(session, "ai_enabled", "false")
