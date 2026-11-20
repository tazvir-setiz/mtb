"""Convert the app's HTML message bodies to the Markdown dialect Bale renders.

Bale ignores the ``parse_mode`` request parameter and always renders message text as
Markdown (see https://docs.bale.ai/markdown-formatting). The whole UI of this project
is written in Telegram HTML, so on Bale every ``<b>``/``<i>``/``<code>`` tag used to be
shown to the user as literal text.

This module parses that HTML and re-renders it using the subset Bale documents:

* ``<b>``/``<strong>`` -> ``*bold*``
* ``<i>``/``<em>`` -> ``_italic_``
* ``<code>`` -> ``` `code` ```
* ``<pre>`` -> fenced code block
* ``<a href="...">label</a>`` -> ``[label](href)``

Tags Bale has no equivalent for (``<u>``, ``<s>``, ``<blockquote>``, ``<tg-spoiler>`` …)
are dropped while their text is kept, so nothing is lost and no raw markup leaks.

Bale's Markdown wants a space before the opening and after the closing ``*``/``_``
marker, so the renderer inserts padding where the neighbouring character is not
whitespace already.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser

_BOLD_TAGS = {"b", "strong"}
_ITALIC_TAGS = {"i", "em"}
_CODE_TAGS = {"code"}
_PRE_TAGS = {"pre"}
_LINK_TAGS = {"a"}

# Tags that carry no formatting on Bale: keep the text, drop the tag.
_TRANSPARENT_TAGS = {
    "blockquote",
    "del",
    "div",
    "ins",
    "p",
    "s",
    "section",
    "small",
    "span",
    "strike",
    "tg-spoiler",
    "u",
}

Block = list  # children list; a node is either a str or a tuple


class _NodeBuilder(HTMLParser):
    """Parse HTML into a small node tree that :class:`_Renderer` can walk."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: Block = []
        self._children: list[Block] = [self.root]
        self._open: list[str] = []
        self._capture: tuple[str, list[str]] | None = None

    # -- parser callbacks -------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._capture is not None:
            return  # everything inside <code>/<pre> is literal text
        if tag == "br":
            self._children[-1].append("\n")
            return

        attributes = dict(attrs)
        if tag in _LINK_TAGS:
            node: tuple = ("link", [], unescape(attributes.get("href") or ""))
        elif tag in _BOLD_TAGS:
            node = ("bold", [])
        elif tag in _ITALIC_TAGS:
            node = ("italic", [])
        elif tag in _CODE_TAGS or tag in _PRE_TAGS:
            self._capture = (tag, [])
            return
        else:
            # Transparent wrapper, incl. unknown tags: keep the text only.
            node = ("transparent", [])

        self._children[-1].append(node)
        self._open.append(tag)
        self._children.append(node[1])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "br":
            return
        if self._capture is not None:
            self._capture[1].append("\n")
        else:
            self._children[-1].append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture is not None:
            if tag == self._capture[0]:
                captured = "".join(self._capture[1])
                kind = "pre" if tag in _PRE_TAGS else "code"
                self._children[-1].append((kind, captured))
                self._capture = None
            return
        if tag == "br":
            return
        if self._open and self._open[-1] == tag:
            self._open.pop()
            self._children.pop()

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture[1].append(data)
        elif data:
            self._children[-1].append(data)


class _Renderer:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.pad_next = False
        self._bold = False
        self._italic = False

    # -- helpers ----------------------------------------------------------
    @property
    def _last_char(self) -> str:
        for chunk in reversed(self.out):
            if chunk:
                return chunk[-1]
        return ""

    def _text(self, text: str) -> None:
        if not text:
            return
        if self.pad_next:
            self.pad_next = False
            if not text[0].isspace():
                self.out.append(" ")
        self.out.append(text)

    def _open_marker(self, marker: str) -> None:
        last = self._last_char
        if not last or not last.isspace():
            self.out.append(" ")
        self.pad_next = False
        self.out.append(marker)

    def _close_marker(self, marker: str) -> None:
        if self.pad_next:
            self.pad_next = False
            self.out.append(" ")
        self.out.append(marker)
        self.pad_next = True

    # -- renderer ---------------------------------------------------------
    def render(self, nodes: Block) -> None:
        for node in nodes:
            if isinstance(node, str):
                self._text(node)
                continue
            kind = node[0]
            if kind == "bold":
                if self._bold:
                    self.render(node[1])
                else:
                    self._bold = True
                    self._open_marker("*")
                    self.render(node[1])
                    self._bold = False
                    self._close_marker("*")
            elif kind == "italic":
                if self._italic:
                    self.render(node[1])
                else:
                    self._italic = True
                    self._open_marker("_")
                    self.render(node[1])
                    self._italic = False
                    self._close_marker("_")
            elif kind == "code":
                self._text(f"`{node[1].replace('`', '')}`")
            elif kind == "pre":
                self._text(f"```\n{node[1].strip(chr(10))}\n```")
            elif kind == "link":
                label = "".join(_plain(node[1]))
                href = node[2]
                self._text(f"[{label}]({href})" if href else label)
            else:  # transparent wrapper
                self.render(node[1])


def _plain(nodes: Block) -> list[str]:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, str):
            parts.append(node)
        elif node[0] in ("code", "pre"):
            parts.append(node[1])
        else:
            parts.extend(_plain(node[1]))
    return parts


def to_bale_markdown(html: str) -> str:
    """Return *html* rewritten as the Markdown subset Bale renders."""
    if not html:
        return html
    builder = _NodeBuilder()
    builder.feed(html)
    builder.close()
    renderer = _Renderer()
    renderer.render(builder.root)
    rendered = "".join(renderer.out)
    if renderer.pad_next:
        rendered += " "
    return rendered
