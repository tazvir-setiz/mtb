from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app.ai_defaults import FALLBACK_MODEL, NEWS_DOMAINS

from app.config import Settings, settings
from app.database.database import get_session
from app.database.repository import SettingsRepository


@dataclass(frozen=True)
class AISettings:
    enabled: bool
    api_key: str = field(repr=False)
    base_url: str
    model: str
    fallback_model: str = FALLBACK_MODEL
    news_grounding_enabled: bool = True
    news_allowed_domains: tuple[str, ...] = tuple(NEWS_DOMAINS.split(","))


def load_ai_settings(defaults: Settings = settings) -> AISettings:
    with get_session() as session:

        def read(name: str, fallback: str) -> str:
            return SettingsRepository.get(session, f"ai_{name}", default=fallback)

        return AISettings(
            enabled=read("enabled", "true" if defaults.ai_enabled else "false") == "true",
            api_key=read("api_key", defaults.ai_api_key),
            base_url=read("base_url", defaults.ai_base_url),
            model=read("model", defaults.ai_model),
            fallback_model=read("fallback_model", defaults.ai_fallback_model),
            news_grounding_enabled=SettingsRepository.get(
                session, "news_grounding_enabled",
                default="true" if defaults.news_grounding_enabled else "false",
            ).lower() in {"true", "1", "yes"},
            news_allowed_domains=parse_domains(SettingsRepository.get(
                session, "news_allowed_domains", default=defaults.news_allowed_domains,
            )),
        )


def parse_domains(value: str) -> tuple[str, ...]:
    """Invalid stored configuration fails closed (no permitted domains)."""
    import ipaddress
    import re

    domains = tuple(dict.fromkeys(x.strip().lower().rstrip(".") for x in value.split(",") if x.strip()))
    for domain in domains:
        if len(domain) > 253 or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", domain
        ):
            return ()
        try:
            ipaddress.ip_address(domain)
        except ValueError:
            continue
        return ()
    return domains


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
    elif name in {"model", "fallback_model"}:
        if len(value) > 200 or any(ord(char) < 32 for char in value):
            return "نام مدل معتبر نیست."
    return None


def save_ai_value(name: str, value: str) -> None:
    if name not in {"enabled", "api_key", "base_url", "model", "fallback_model",
                    "news_grounding_enabled", "news_allowed_domains"}:
        raise ValueError("Unknown AI setting")
    if name == "news_grounding_enabled" and value not in {"true", "false"}:
        raise ValueError("Expected true or false")
    if name == "news_allowed_domains" and value and not parse_domains(value):
        raise ValueError("Expected comma-separated public domain names")
    if name == "fallback_model" and value and validate_ai_value(name, value):
        raise ValueError("Invalid fallback model")
    current = load_ai_settings()
    with get_session() as session:
        key = name if name.startswith("news_") else f"ai_{name}"
        SettingsRepository.set(session, key, value)
        if name == "base_url" and value != current.base_url:
            SettingsRepository.set(session, "ai_api_key", "")
            SettingsRepository.set(session, "ai_enabled", "false")
        if name == "api_key" and not value:
            SettingsRepository.set(session, "ai_enabled", "false")
