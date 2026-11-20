"""Answer Telegram/Bale callback queries exactly once.

A callback query can be acknowledged only once: the moment ``answerCallbackQuery`` runs, the
query id is consumed and every later call fails with ``BadRequest: Query is too old and response
timeout expired or query id is invalid``.  The router used to answer before dispatch (to stop the
client's loading spinner) while a handler answered again to show a toast or an alert, so that
second answer raised, the router logged "Telegram rejected callback" and told the admin the page
could not be shown - right after the page had in fact been rendered.

:func:`ack` makes the acknowledgement idempotent: the first call for a query wins, later calls
are silent no-ops, and an expired/consumed query counts as answered instead of as a failure.
Acknowledgement is UI feedback only, so it never raises and never blocks the handler's result.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any

from telegram.error import TelegramError

logger = logging.getLogger(__name__)

# Recently acknowledged query ids.  The router's own acknowledgement and the handler's toast
# happen within milliseconds of each other, so a small window is enough to deduplicate them.
_MAX_TRACKED = 512

_answered: OrderedDict[str, None] = OrderedDict()

# Substrings of the BadRequest Telegram/Bale return when a query id is no longer usable.
_STALE_MARKERS = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
    "query_id_invalid",
)


def is_stale_query_error(exc: BaseException) -> bool:
    """Return whether *exc* means the callback query was already consumed or expired."""
    message = str(exc).lower()
    return any(marker in message for marker in _STALE_MARKERS)


def _query_id(query: Any) -> str | None:
    query_id = getattr(query, "id", None)
    return str(query_id) if query_id else None


def _remember(query_id: str) -> None:
    _answered[query_id] = None
    _answered.move_to_end(query_id)
    while len(_answered) > _MAX_TRACKED:
        _answered.popitem(last=False)


def already_answered(query: Any) -> bool:
    """Return whether :func:`ack` already acknowledged *query*."""
    query_id = _query_id(query)
    return query_id is not None and query_id in _answered


async def ack(query: Any, text: str | None = None, show_alert: bool = False) -> bool:
    """Acknowledge *query* unless it has already been acknowledged.

    ``text`` is shown as a toast (or as a modal alert when ``show_alert`` is true), exactly like
    ``CallbackQuery.answer``.  Returns ``True`` only for the call that actually acknowledged the
    query, so callers can fall back to a regular message when the toast can no longer be shown.
    """
    if query is None:
        return False

    query_id = _query_id(query)
    if query_id is not None:
        if query_id in _answered:
            return False
        _remember(query_id)

    try:
        if text is None:
            await query.answer()
        else:
            await query.answer(text, show_alert=show_alert)
    except TelegramError as exc:
        logger.debug("Callback acknowledgement skipped (%s): %s", type(exc).__name__, exc)
        return False
    return True
