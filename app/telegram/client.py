from __future__ import annotations

import logging
import sys
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

from app.config import ConfigError, settings
from app.telegram.bale_bot import BaleBot
from app.telegram.bot_proxy import get_bot_api_proxy_url

logger = logging.getLogger(__name__)

_bot_instance: Bot | None = None
_client: BotClient | Any | None = None


def set_bot(bot: Bot) -> None:
    global _bot_instance, _client
    _bot_instance = bot
    if _client is not None and isinstance(_client, BotClient):
        _client.bot = bot


def _create_default_bot() -> Bot:
    if settings.platform == "bale":
        return BaleBot(
            token=settings.bot_token,
            base_url=settings.bot_base_url,
            base_file_url=settings.bot_base_file_url,
        )

    kwargs: dict[str, Any] = {
        "token": settings.bot_token,
    }
    proxy_url = get_bot_api_proxy_url()
    if proxy_url:
        kwargs["proxy"] = proxy_url

    return Bot(**kwargs)


class BotMessage:
    """Lightweight compatible wrapper for messages."""

    def __init__(
        self,
        message_id: int,
        text: str = "",
        chat_id: int | None = None,
        entities: list | None = None,
        media: Any = None,
        poll: Any = None,
    ):
        self.id = message_id
        self.message_id = message_id
        self.message = text
        self.text = text
        self.caption = text if media else None
        self.text_html = text
        self.caption_html = text if media else None
        self.chat_id = chat_id
        self.entities = entities or []
        self.media = media
        self.poll = poll


class BotClient:
    """Bot-based client replacing MTProto/Telethon user session."""

    def __init__(self, bot: Bot | None = None):
        self.bot = bot or _bot_instance or _create_default_bot()
        self._connected: bool = False
        self._cache: dict[tuple[int, int], Any] = {}
        self._event_handlers: list[Any] = []

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_user_authorized(self) -> bool:
        # Bot token acts as full authorization; no user SMS/phone code needed.
        return True

    async def get_me(self) -> Any:
        return await self.bot.get_me()

    async def get_chat(self, chat_id: int | str) -> Any:
        return await self.bot.get_chat(chat_id)

    async def get_chat_member(self, chat_id: int | str, user_id: int) -> Any:
        return await self.bot.get_chat_member(chat_id, user_id)

    def cache_message(self, source_id: int, message: Any) -> None:
        msg_id = getattr(message, "id", None) or getattr(message, "message_id", None)
        if msg_id is not None:
            if len(self._cache) > 1000:
                first_key = next(iter(self._cache))
                self._cache.pop(first_key, None)
            self._cache[(source_id, msg_id)] = message

    async def get_messages(self, entity: int | str, ids: list[int]) -> list[Any]:
        results = []
        entity_id = int(entity) if str(entity).lstrip("-").isdigit() else entity
        for msg_id in ids:
            cached = self._cache.get((entity_id, msg_id))
            if cached is not None:
                results.append(cached)
            else:
                results.append(BotMessage(message_id=msg_id, text="", chat_id=entity_id))
        return results

    async def send_message(
        self,
        entity: int | str,
        message: str,
        file: Any = None,
        parse_mode: str | None = "html",
        link_preview: bool = False,
        **kwargs: Any,
    ) -> Any:
        pm = ParseMode.HTML if str(parse_mode).lower() == "html" else parse_mode
        if file is not None:
            if isinstance(file, str) or hasattr(file, "file_id"):
                return await self.bot.send_photo(
                    chat_id=entity,
                    photo=file,
                    caption=message,
                    parse_mode=pm,
                )
            return await self.bot.send_document(
                chat_id=entity,
                document=file,
                caption=message,
                parse_mode=pm,
            )
        return await self.bot.send_message(
            chat_id=entity,
            text=message,
            parse_mode=pm,
            disable_web_page_preview=not link_preview,
        )

    async def copy_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        caption: str | None = None,
        parse_mode: str | None = "html",
        **kwargs: Any,
    ) -> Any:
        pm = ParseMode.HTML if str(parse_mode).lower() == "html" else parse_mode
        return await self.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption,
            parse_mode=pm,
            **kwargs,
        )

    async def forward_messages(
        self,
        entity: int | str,
        messages: int | list[int],
        from_peer: int | str,
        drop_author: bool = True,
        **kwargs: Any,
    ) -> Any:
        msg_id = messages if isinstance(messages, int) else messages[0]
        if drop_author:
            return await self.bot.copy_message(
                chat_id=entity,
                from_chat_id=from_peer,
                message_id=msg_id,
            )
        return await self.bot.forward_message(
            chat_id=entity,
            from_chat_id=from_peer,
            message_id=msg_id,
        )

    async def get_dialogs(self, limit: int = 50) -> list[Any]:
        return []

    def add_event_handler(self, handler: Any, event_filter: Any = None) -> None:
        if handler not in self._event_handlers:
            self._event_handlers.append(handler)

    def remove_event_handler(self, handler: Any) -> None:
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)


def get_client() -> Any:
    global _client
    if _client is None:
        _client = BotClient(_bot_instance)
    return _client


async def ensure_started(bot: Bot | None = None) -> Any:
    if bot is not None:
        set_bot(bot)
    client = get_client()
    if not client.is_connected():
        await client.connect()

    # For backward compatibility if someone mocks get_client with an unauthorized Telethon mock
    if hasattr(client, "is_user_authorized") and not await client.is_user_authorized():
        from telethon.errors import SessionPasswordNeededError

        if not sys.stdin or not sys.stdin.isatty():
            if hasattr(client, "disconnect"):
                await client.disconnect()
            raise ConfigError(
                "Telethon session is not authorized and interactive login is unavailable. "
                "Generate TELETHON_STRING_SESSION locally with python -m scripts.export_session "
                "and set it in Railway Variables before deploying. "
                "If a revoked session already exists on the volume, replace that session file."
            )
        logger.warning("Session is not authorized; starting interactive login.")
        try:
            await client.start()  # type: ignore[func-returns-value]
        except SessionPasswordNeededError:
            logger.error("Two-Step Verification password required.")
            raise

    try:
        if hasattr(client, "get_dialogs"):
            await client.get_dialogs(limit=50)
    except Exception:
        logger.debug("Could not pre-fetch dialogs", exc_info=True)
    return client


async def stop_client() -> None:
    global _client
    if _client is not None:
        if hasattr(_client, "disconnect"):
            await _client.disconnect()
