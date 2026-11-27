import re
from html import unescape
from urllib.parse import unquote

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.services.html_sanitizer import HTMLSanitizer

USERNAME_SETTING = "message_username_replacement"
USERNAME = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{0,31}(?!\w)")
VALID_USERNAME = re.compile(r"@[A-Za-z][A-Za-z0-9_]{4,31}\Z")
URL = re.compile(r"(?:https?://|www\.|(?:t|telegram)\.me/)[^\s<>]+", re.IGNORECASE)
SHORT_URL = re.compile(
    r"\b(?:bit\.ly|tinyurl\.com|t\.co|is\.gd|goo\.gl|b2n\.ir|yun\.ir|cutt\.ly|rebrand\.ly)/[^\s<>]+",
    re.I,
)
MARKDOWN_LINK = re.compile(r"\[([^\]\n]*)\]\([^\s)]*\)")
GENERIC_LINK_LABELS = frozenset(
    {"link", "لینک", "مشاهده", "ادامه", "ادامه مطلب", "مشروح خبر", "منبع", "سایت", "اینجا", "کلیک کنید"}
)


def _replace_markdown_link(match: re.Match[str]) -> str:
    label = match.group(1).strip()
    if label.casefold() in GENERIC_LINK_LABELS:
        return ""
    return match.group(1)


def remove_urls(data: str) -> str:
    data = MARKDOWN_LINK.sub(_replace_markdown_link, data)
    data = SHORT_URL.sub("", URL.sub("", data))
    return re.sub(
        r"\S*%[0-9a-fA-F]{2}\S*", lambda m: "" if URL.search(unquote(m[0])) else m[0], data
    )


def _strip_trailing_non_text_lines(text: str) -> str:
    lines = text.splitlines()
    while lines and not any(ch.isalnum() for ch in lines[-1]):
        lines.pop()
    return "\n".join(lines).rstrip()


def username_replacement() -> str:
    with get_session() as session:
        value = SettingsRepository.get(session, USERNAME_SETTING, default="")
    return value if value and VALID_USERNAME.fullmatch(value) else ""


def sanitize_text(text: str, *, remove_links: bool, replacement: str | None = None) -> str:
    if replacement is None:
        replacement = username_replacement()

    def transform(data: str) -> str:
        if remove_links:
            data = remove_urls(data)
        return USERNAME.sub(lambda _: replacement, data)

    rendered = HTMLSanitizer(transform, remove_links).render(text)
    if remove_links:
        rendered = _strip_trailing_non_text_lines(rendered)
    return rendered


def publication_is_clean(text: str, *, replacement: str | None = None) -> bool:
    plain = unescape(re.sub(r"<[^>]*>", " ", text))
    plain = unquote(plain)
    if URL.search(plain) or SHORT_URL.search(plain):
        return False
    if replacement is None:
        replacement = username_replacement()
    return all(match[0] == replacement for match in USERNAME.finditer(plain))
