import re

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.services.html_sanitizer import HTMLSanitizer

USERNAME_SETTING = "message_username_replacement"
USERNAME = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{0,31}(?!\w)")
VALID_USERNAME = re.compile(r"@[A-Za-z][A-Za-z0-9_]{4,31}\Z")
URL = re.compile(r"(?:https?://|www\.|(?:t|telegram)\.me/)[^\s<>]+", re.IGNORECASE)
MARKDOWN_LINK = re.compile(r"\[([^\]\n]*)\]\([^\s)]*\)")


def username_replacement() -> str:
    with get_session() as session:
        value = SettingsRepository.get(session, USERNAME_SETTING, default="")
    return value if value and VALID_USERNAME.fullmatch(value) else ""


def sanitize_text(text: str, *, remove_links: bool) -> str:
    replacement = username_replacement()

    def transform(data: str) -> str:
        if remove_links:
            data = MARKDOWN_LINK.sub(r"\1", data)
            data = URL.sub("", data)
        return USERNAME.sub(lambda _: replacement, data)

    return HTMLSanitizer(transform, remove_links).render(text)
