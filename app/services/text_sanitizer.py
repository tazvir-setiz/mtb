"""Apply the administrator's username rule without relying on model compliance."""

import re
from html import escape
from html.parser import HTMLParser

from app.database.database import get_session
from app.database.repository import SettingsRepository

USERNAME_SETTING = "message_username_replacement"
USERNAME = re.compile(r"(?<![\w@])@[A-Za-z][A-Za-z0-9_]{0,31}(?!\w)")
VALID_USERNAME = re.compile(r"@[A-Za-z][A-Za-z0-9_]{4,31}\Z")
URL = re.compile(r"(?:https?://|www\.|(?:t|telegram)\.me/)[^\s<>]+", re.IGNORECASE)
MARKDOWN_LINK = re.compile(r"\[([^\]\n]*)\]\([^\s)]*\)")


def username_replacement() -> str:
    with get_session() as session:
        value = SettingsRepository.get(session, USERNAME_SETTING, default="")
    return value if value and VALID_USERNAME.fullmatch(value) else ""


class _Sanitizer(HTMLParser):
    def __init__(self, replacement: str, remove_links: bool):
        super().__init__(convert_charrefs=True)
        self.replacement = replacement
        self.remove_links = remove_links
        self.parts: list[str] = []
        self.suppressed = 0
        self.stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        allowed = tag in {
            "b",
            "strong",
            "i",
            "em",
            "u",
            "ins",
            "s",
            "strike",
            "del",
            "code",
            "pre",
            "blockquote",
            "tg-spoiler",
        }
        if tag == "a" and not self.remove_links:
            href = dict(attrs).get("href", "")
            if href and not re.match(r"(?:https?://)?(?:t|telegram)\.me/|tg://user", href, re.I):
                self.parts.append(f'<a href="{escape(href, quote=True)}">')
                self.stack.append((tag, True))
                return
        self.stack.append((tag, allowed))
        if allowed:
            self.parts.append(self.get_starttag_text() if not self.remove_links else f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)
            return
        if self.suppressed:
            return
        if self.stack and self.stack[-1][0] == tag:
            _, allowed = self.stack.pop()
            if allowed:
                self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.suppressed:
            return
        if self.remove_links:
            data = MARKDOWN_LINK.sub(r"\1", data)
            data = URL.sub("", data)
        data = USERNAME.sub(lambda _: self.replacement, data)
        self.parts.append(escape(data, quote=False))


def sanitize_text(text: str, *, remove_links: bool) -> str:
    parser = _Sanitizer(username_replacement(), remove_links)
    parser.feed(text)
    parser.close()
    while parser.stack:
        tag, allowed = parser.stack.pop()
        if allowed:
            parser.parts.append(f"</{tag}>")
    return "".join(parser.parts).strip()
