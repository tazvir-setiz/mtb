"""A :class:`telegram.Bot` subclass that speaks Bale's formatting dialect.

Bale has no ``parse_mode`` parameter and always renders Markdown, so every message the
application sends through python-telegram-bot has to be converted from the HTML this
codebase uses (see :mod:`app.telegram.bale_format`).

All Bot methods funnel their payload through :meth:`telegram.Bot._do_post`, so
overriding that single hook rewrites outgoing text/captions for *every* send, edit,
copy and media call without touching the ~100 call sites.
"""

from __future__ import annotations

from typing import Any

from telegram.ext import Defaults, ExtBot

from app.telegram.bale_format import to_bale_markdown

_TEXT_KEYS = ("text", "caption")


def _is_html(parse_mode: Any) -> bool:
    return parse_mode is not None and str(parse_mode).lower() == "html"


class BaleBot(ExtBot):
    """Bot that converts Telegram HTML payloads into Bale Markdown before sending.

    ``ExtBot`` is used instead of plain ``Bot`` because ``Defaults(parse_mode=HTML)`` is
    what makes the ~100 UI call sites HTML in the first place; python-telegram-bot only
    applies :class:`telegram.ext.Defaults` on ``ExtBot`` instances.
    """

    def __init__(
        self,
        *args: Any,
        defaults: Defaults | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, defaults=defaults, **kwargs)

    async def _do_post(
        self,
        endpoint: str,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> bool | dict[str, Any] | list[dict[str, Any]]:
        if _is_html(data.get("parse_mode")):
            converted = dict(data)
            for key in _TEXT_KEYS:
                value = converted.get(key)
                if isinstance(value, str) and value:
                    converted[key] = to_bale_markdown(value)
            # Bale ignores this parameter; drop it so logs show what is really sent.
            converted.pop("parse_mode", None)
            data = converted
        return await super()._do_post(endpoint, data, **kwargs)
