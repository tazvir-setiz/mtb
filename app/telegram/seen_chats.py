"""Remember chats the bot has seen so a channel can be configured without getChat.

Bale's Bot API does not reliably resolve a channel from an id or ``@username``:
``getChat`` answers "chat not found" even when the bot is a member/administrator of
the channel. The only trustworthy source of a channel's id is an incoming update
(the ``channel_post`` message, or the ``my_chat_member`` service update Bale sends
when the bot is added to a channel).

This module keeps a small, persisted list of those chats. The channel setup flow can
then show the ids to the admin and fall back to the saved chat when ``getChat`` fails.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database.database import get_session
from app.database.repository import SettingsRepository

logger = logging.getLogger(__name__)

KEY = "seen_chats"
MAX_ENTRIES = 30
CHAT_TYPES = {"channel", "supergroup", "group"}

_known_ids: set[int] = set()


def _load(session) -> list[dict]:
    raw = SettingsRepository.get(session, KEY)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Ignoring malformed %s setting", KEY)
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for item in data:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        try:
            item = dict(item, id=int(item["id"]))
        except (TypeError, ValueError):
            continue
        entries.append(item)
        _known_ids.add(item["id"])
    return entries[:MAX_ENTRIES]


def record(chat: Any) -> dict | None:
    """Persist *chat* (a channel/group) if it is not stored yet."""
    if chat is None:
        return None
    chat_id = getattr(chat, "id", None)
    chat_type = (getattr(chat, "type", "") or "").lower()
    if chat_id is None or chat_type not in CHAT_TYPES:
        return None
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        return None

    username = getattr(chat, "username", None) or None
    title = (getattr(chat, "title", None) or "").strip()
    if chat_id in _known_ids:
        return None

    entry = {"id": chat_id, "title": title, "username": username, "type": chat_type}
    with get_session() as session:
        entries = _load(session)
        for item in entries:
            if item["id"] == chat_id:
                _known_ids.add(chat_id)
                return item
        entries.insert(0, entry)
        SettingsRepository.set(
            session, KEY, json.dumps(entries[:MAX_ENTRIES], ensure_ascii=False)
        )
    _known_ids.add(chat_id)
    logger.info(
        "Chat seen by bot id=%s type=%s title=%s username=%s",
        chat_id,
        chat_type,
        title,
        username,
    )
    return entry


def recent(limit: int = 5) -> list[dict]:
    """Newest seen chats first."""
    with get_session() as session:
        return _load(session)[:limit]


def clear() -> None:
    _known_ids.clear()
    with get_session() as session:
        SettingsRepository.set(session, KEY, "[]")


def find(ref: str | int) -> dict | None:
    """Match a numeric id or a ``@username`` against the stored chats."""
    entries = recent(limit=MAX_ENTRIES)
    text = str(ref).strip()
    if text.lstrip("-+").isdigit():
        target = int(text)
        for item in entries:
            if item["id"] == target:
                return item
        return None
    name = text.lstrip("@").lower()
    if not name:
        return None
    for item in entries:
        username = (item.get("username") or "").lower()
        if username and username == name:
            return item
    return None
