import re
from collections.abc import Callable
from html import escape
from html.parser import HTMLParser

FORMATTING_TAGS = {
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
TELEGRAM_LINK = re.compile(r"(?:https?://)?(?:t|telegram)\.me/|tg://user", re.I)
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


class HTMLSanitizer(HTMLParser):
    def __init__(self, transform_text: Callable[[str], str], remove_links: bool):
        super().__init__(convert_charrefs=True)
        self.transform_text = transform_text
        self.remove_links = remove_links
        self.parts: list[str] = []
        self.suppressed = 0
        self.stack: list[tuple[str, bool]] = []
        self._link_buffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
            return
        if self.suppressed:
            return
        allowed = tag in FORMATTING_TAGS
        if tag == "a" and not self.remove_links:
            href = dict(attrs).get("href", "")
            if href and not TELEGRAM_LINK.match(href):
                self.parts.append(f'<a href="{escape(href, quote=True)}">')
                self.stack.append((tag, True))
                return
        if tag == "a" and self.remove_links:
            self.stack.append((tag, False))
            if self._link_buffer is None:
                self._link_buffer = []
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
            if tag == "a" and self.remove_links and self._link_buffer is not None:
                buffered = "".join(self._link_buffer)
                self._link_buffer = None
                if buffered.strip().casefold() not in GENERIC_LINK_LABELS:
                    self.parts.append(buffered)
                return
            if allowed:
                self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self.suppressed:
            return
        rendered = escape(self.transform_text(data), quote=False)
        if self._link_buffer is not None:
            self._link_buffer.append(rendered)
        else:
            self.parts.append(rendered)

    def render(self, text: str) -> str:
        self.feed(text)
        self.close()
        while self.stack:
            tag, allowed = self.stack.pop()
            if allowed:
                self.parts.append(f"</{tag}>")
        return "".join(self.parts).strip()
