from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any

from telethon import events

from app.database.database import get_session
from app.database.models import ChannelType, JobStatus, MessageStatus
from app.database.repository import (
    ChannelRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.log_context import traced
from app.services.fanout import fan_out
from app.services.message_locks import message_lock
from app.telegram.message_sender import prepare_message, send_prepared_message

logger = logging.getLogger(__name__)

SETTING_KEY = "auto_forward_enabled"
_AUTO_JOB_MARKER = -1

_handler = None  # type: ignore[var-annotated]
_registered_client: Any | None = None
_route_map: dict[int, list[tuple[int, int]]] = {}


class ProcessingLimiter:
    """Bounded concurrency limiter with an asyncio.Lock-compatible interface."""

    def __init__(self, max_concurrent: int = 5):
        self._max = max_concurrent
        self._active = 0
        self._sem = asyncio.Semaphore(max_concurrent)

    async def acquire(self):
        await self._sem.acquire()
        self._active += 1

    def release(self):
        self._active = max(0, self._active - 1)
        self._sem.release()

    def locked(self) -> bool:
        return self._active > 0

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


_processing_lock = ProcessingLimiter(max_concurrent=5)
_waiting = 0
_counts = Counter()


def status_snapshot():
    return dict(
        listener_active=_handler is not None or is_enabled(),
        waiting=_waiting,
        processing=_processing_lock.locked(),
        **_counts,
    )


@asynccontextmanager
async def processing_slot():
    global _waiting
    started = time.monotonic()
    _waiting += 1
    _counts["received"] += 1
    try:
        await _processing_lock.acquire()
    finally:
        _waiting -= 1
    try:
        yield
    finally:
        _processing_lock.release()
        logger.info(
            "Processing finished total_elapsed=%.2fs waiting=%d",
            time.monotonic() - started,
            _waiting,
        )


def is_enabled() -> bool:
    with get_session() as session:
        return SettingsRepository.get(session, SETTING_KEY, default="0") == "1"


def _set_enabled(value: bool) -> None:
    with get_session() as session:
        SettingsRepository.set(session, SETTING_KEY, "1" if value else "0")


def _get_auto_job_id(source_id: int, destination_id: int) -> int:
    with get_session() as session:
        job = ForwardJobRepository.create(
            session,
            source_id,
            destination_id,
            _AUTO_JOB_MARKER,
            _AUTO_JOB_MARKER,
            0,
        )
        ForwardJobRepository.update_status(session, job, JobStatus.RUNNING)
        return job.id


@traced
async def _on_new_message(
    event: Any,
    source_id: int,
    routes: list[tuple[int, int]],
    *,
    listener: Any = None,
) -> None:
    async with processing_slot():
        if listener is not None and listener is not _handler:
            _counts["stale"] += 1
            return

        client = getattr(event, "client", None) or _registered_client
        msg = getattr(event, "message", None) or event
        msg_id = getattr(msg, "id", None) or getattr(msg, "message_id", None)

        if client and hasattr(client, "cache_message") and msg_id is not None:
            client.cache_message(source_id, msg)

        async with message_lock(source_id, msg_id, None):
            with get_session() as session:
                signature = SettingsRepository.get(session, "signature_text")
            outcomes = await fan_out(
                client,
                msg,
                source_id,
                routes,
                signature,
                prepare_message,
                send_prepared_message,
            )
            for status in outcomes.values():
                _counts[
                    {
                        MessageStatus.SUCCESS: "sent",
                        MessageStatus.DUPLICATE: "duplicates",
                        MessageStatus.SKIPPED: "skipped",
                        MessageStatus.FAILED: "failed",
                    }[status]
                ] += 1


def _channel_aliases(channel_id: int) -> set[int]:
    aliases = {channel_id}
    try:
        from telethon.utils import get_peer_id, resolve_id

        marked = get_peer_id(channel_id)
        aliases.add(marked)
        raw_id, _ = resolve_id(channel_id)
        aliases.add(raw_id)
        aliases.add(int(f"-100{raw_id}"))
    except Exception:
        pass
    s = str(channel_id)
    if s.startswith("-100") and len(s) < 14:
        try:
            legacy_raw = int(s[4:])
            aliases.add(legacy_raw)
            aliases.add(-1000000000000 - legacy_raw)
        except Exception:
            pass
    return aliases


def _build_route_map() -> tuple[bool, list[int], list[int], set[int]]:
    global _route_map
    with get_session() as session:
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)

    if not sources or not destinations:
        _route_map = {}
        return False, [], [], set()

    source_ids = [channel.telegram_id for channel in sources]
    destination_ids = [channel.telegram_id for channel in destinations]
    new_map: dict[int, list[tuple[int, int]]] = {}
    chats: set[int] = set()
    for source_id in source_ids:
        routes = [
            (destination_id, _get_auto_job_id(source_id, destination_id))
            for destination_id in destination_ids
        ]
        for alias in _channel_aliases(source_id):
            new_map[alias] = routes
            chats.add(alias)
    _route_map = new_map
    return True, source_ids, destination_ids, chats


async def handle_channel_update(update: Any, context: Any = None) -> None:
    """Entry point for incoming channel posts from python-telegram-bot Application."""
    if not is_enabled():
        return

    msg = (
        getattr(update, "channel_post", None)
        or getattr(update, "message", None)
        or getattr(update, "effective_message", None)
    )
    if msg is None:
        return

    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    if chat_id is None:
        chat_id = getattr(msg, "chat_id", None) or getattr(getattr(msg, "chat", None), "id", None)
    if chat_id is None:
        return

    routes = _route_map.get(chat_id)
    if routes is None:
        for alias in _channel_aliases(chat_id):
            if alias in _route_map:
                routes = _route_map[alias]
                break

    if not routes:
        if not _route_map:
            _build_route_map()
            routes = _route_map.get(chat_id)
            if routes is None:
                for alias in _channel_aliases(chat_id):
                    if alias in _route_map:
                        routes = _route_map[alias]
                        break

    if not routes:
        return

    from types import SimpleNamespace

    from app.telegram.client import get_client, set_bot

    bot = getattr(context, "bot", None) if context else None
    if bot:
        set_bot(bot)
    client = _registered_client or get_client()

    event = SimpleNamespace(client=client, message=msg, chat_id=chat_id)
    await _on_new_message(event, chat_id, routes, listener=_handler)


async def start_listener(client: Any) -> bool:
    global _handler, _registered_client
    await stop_listener(client)
    routes_built, source_ids, destination_ids, chats_to_listen = _build_route_map()
    if not routes_built:
        return False

    async def handler(event):
        chat_id = getattr(event, "chat_id", None)
        if chat_id is None:
            return
        routes = _route_map.get(chat_id)
        if routes is None:
            for alias in _channel_aliases(chat_id):
                if alias in _route_map:
                    routes = _route_map[alias]
                    break
        if not routes:
            return
        await _on_new_message(
            event,
            chat_id,
            routes,
            listener=handler,
        )

    if hasattr(client, "add_event_handler"):
        try:
            client.add_event_handler(handler, events.NewMessage(chats=list(chats_to_listen)))
        except Exception:
            client.add_event_handler(handler)

    _handler = handler
    _registered_client = client
    logger.info(
        "Auto-forward listener started sources=%s destinations=%s",
        source_ids,
        destination_ids,
    )
    return True


async def stop_listener(client: Any | None = None) -> None:
    global _handler, _registered_client, _route_map
    target_client = client or _registered_client
    if _handler is not None and target_client is not None and hasattr(target_client, "remove_event_handler"):
        try:
            target_client.remove_event_handler(_handler)
        except Exception:
            pass
    _handler = None
    _registered_client = None
    _route_map = {}


async def enable(client: Any) -> bool:
    try:
        started = await start_listener(client)
    except Exception:
        _set_enabled(False)
        raise
    _set_enabled(started)
    return started


async def disable(client: Any | None = None) -> None:
    await stop_listener(client)
    _set_enabled(False)


async def sync_on_startup(client: Any) -> bool:
    return await refresh_listener(client)


async def refresh_listener(client: Any) -> bool:
    if not is_enabled():
        return False
    try:
        return await enable(client)
    except Exception:
        logger.exception("Could not refresh auto-forward listener")
        await disable(client)
        return False
