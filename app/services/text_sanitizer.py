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
    {
        "link",
        "لینک",
        "مشاهده",
        "مشاهده خبر",
        "ادامه",
        "ادامه مطلب",
        "ادامه خبر",
        "مشروح خبر",
        "بیشتر بخوانید",
        "متن کامل",
        "جزئیات",
        "جزئیات بیشتر",
        "لینک خبر",
        "مطالعه بیشتر",
        "منبع",
        "سایت",
        "اینجا",
        "اینجا کلیک کنید",
        "کلیک",
        "کلیک کنید",
        "تلگرام",
        "ایتا",
        "بله",
        "روبیکا",
        "سروش",
        "سروش پلاس",
        "آپارات",
        "اینستاگرام",
        "یوتیوب",
        "توییتر",
        "ایکس",
    }
)
TRAILING_FOOTER_HEADERS = frozenset(
    {
        "دریافت آخرین اخبار",
        "آخرین اخبار",
        "ما را دنبال کنید",
        "ما را در شبکه‌های اجتماعی دنبال کنید",
        "ارتباط با ما",
    }
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


def _is_trailing_noise_line(line: str) -> bool:
    if not any(ch.isalnum() for ch in line):
        return True
    stripped = re.sub(r"^[\W_]+|[\W_]+$", "", line).strip()
    if stripped.casefold() in GENERIC_LINK_LABELS or stripped in TRAILING_FOOTER_HEADERS:
        return True
    if "|" in stripped:
        parts = [re.sub(r"^[\W_]+|[\W_]+$", "", part).strip().casefold() for part in stripped.split("|")]
        if parts and all(not part or part in GENERIC_LINK_LABELS for part in parts):
            return True
    return False


def _strip_trailing_non_text_lines(text: str) -> str:
    lines = text.splitlines()
    while lines and _is_trailing_noise_line(lines[-1]):
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
