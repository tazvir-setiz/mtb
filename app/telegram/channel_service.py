from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.telegram import seen_chats

logger = logging.getLogger(__name__)


class ChannelAccessError(Exception):
    """کانال یافت نشد یا دسترسی کافی وجود ندارد."""


@dataclass
class ChannelInfo:
    telegram_id: int
    title: str
    username: str | None
    is_admin: bool
    can_post: bool


_NOT_FOUND = "کانال یافت نشد. شناسه یا Username را بررسی کنید."
_BALE_HINT = (
    "در بله مطمئن شوید ربات به کانال اضافه شده و Administrator است. "
    "مطمئن‌ترین راه، ارسال شناسهٔ عددی کانال است (از اطلاعات کانال یا getUpdates)."
)
_INVITE_LINK_HINT = (
    "لینک دعوت برای شناسایی کانال کافی نیست. "
    "شناسهٔ عددی یا Username کانال را ارسال کنید."
)

_INVITE_RE = re.compile(r"^(?:https?://)?(?:ble\.ir/join|t\.me/(?:joinchat|\+))", re.I)
_BALE_POST_RE = re.compile(r"^(?:https?://)?(?:ble\.ir|bale\.ai)/post/([^/?#]+)", re.I)
_BALE_WEB_RE = re.compile(r"^(?:https?://)?(?:web\.)?bale\.ai/", re.I)
_TME_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:t|telegram)\.me/", re.I)


def _is_digits(value: str) -> bool:
    return value.lstrip("-+").isdigit()


def normalize_channel_ref(raw: str) -> str | int:
    raw = raw.strip()
    if not raw:
        return raw
    if raw.startswith("@"):
        return raw
    if _is_digits(raw):
        try:
            return int(raw)
        except ValueError:
            return raw

    # Telegram links
    if "/c/" in raw and _TME_RE.match(raw):
        part = raw.split("/c/")[-1].strip("/").split("/")[0]
        if part.isdigit():
            return int(f"-100{part}")
    if _TME_RE.match(raw):
        tail = _TME_RE.sub("", raw).strip("/")
        if tail.startswith("+"):
            return raw  # invite link: cannot be resolved by the API
        username = tail.split("/")[0]
        if username:
            return f"@{username}"

    # Bale links
    if _INVITE_RE.match(raw):
        return raw  # resolved (rejected) before this point; kept for callers
    match = _BALE_POST_RE.match(raw)
    if match and _is_digits(match.group(1)):
        # ble.ir/post/<group_id>/<message_id>/<date> identifies a group/channel.
        return int(match.group(1))
    if _BALE_WEB_RE.match(raw):
        # web.bale.ai/chat?uid=<id> is what the Bale web client puts in the address bar.
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        params = parse_qs(parsed.query)
        for key in ("uid", "gid", "chat_id", "chat", "id"):
            value = params.get(key, [""])[0]
            if _is_digits(value):
                return int(value)
    ble_link = re.match(r"^(?:https?://)?(?:www\.)?ble\.ir/(.+)$", raw, re.I)
    if ble_link:
        part = ble_link.group(1).strip("/").split("/")[0]
        if part and part.lower() != "join":
            return f"@{part}"

    return raw if raw.startswith("@") else "@" + raw


def _lookup_candidates(ref: str | int) -> list[str | int]:
    """Refs to try against ``getChat``.

    Bale chat ids are quirky: channel/group ids can be negative while the same entity
    shows a positive id in web links, and usernames may or may not want the ``@``.
    On Bale we therefore try the documented alternatives before giving up. Telegram
    keeps the single, exact ref.
    """
    candidates: list[str | int] = [ref]
    if settings.platform != "bale":
        return candidates

    def add(value: str | int) -> None:
        if value not in candidates:
            candidates.append(value)

    if isinstance(ref, int):
        # String form first: Bale ids can exceed 2**53 and lose precision as JSON numbers.
        candidates.insert(0, str(ref))
        if ref > 0:
            add(-ref)
    elif isinstance(ref, str):
        if ref.startswith("@"):
            add(ref[1:])
        elif _is_digits(ref):
            numeric = int(ref)
            add(numeric)
            if numeric > 0:
                add(-numeric)
    return candidates


def _not_found_message() -> str:
    if settings.platform == "bale":
        return f"{_NOT_FOUND}\n\n{_BALE_HINT}"
    return (
        f"{_NOT_FOUND}\n\n"
        "مطمئن شوید ربات به کانال اضافه و Administrator شده است."
    )


async def _channel_info_from_seen(client: Any, cached: dict) -> ChannelInfo:
    """Build channel info from a chat the bot has already received an update from."""
    chat_id = int(cached["id"])
    is_admin = False
    can_post = False
    try:
        me = await client.get_me()
        bot_id = getattr(me, "id", None)
        if bot_id:
            member = await client.get_chat_member(chat_id, bot_id)
            status = getattr(member, "status", "")
            if status == "creator":
                is_admin = True
                can_post = True
            elif status == "administrator":
                is_admin = True
                can_post = bool(getattr(member, "can_post_messages", True))
    except Exception:
        is_admin = False
        can_post = False
    return ChannelInfo(
        telegram_id=chat_id,
        title=cached.get("title") or "بدون نام",
        username=cached.get("username"),
        is_admin=is_admin,
        can_post=can_post,
    )


async def _resolve_bot_chat(client: Any, ref: str | int) -> ChannelInfo:
    try:
        chat = await client.get_chat(ref)
    except Exception as exc:
        # Bale often cannot resolve a channel through getChat. Fall back to chats the
        # bot has actually received updates from (channel_post / my_chat_member).
        cached = seen_chats.find(ref)
        if cached is None:
            raise ChannelAccessError(_NOT_FOUND) from exc
        logger.info(
            "Channel resolved from a chat the bot has seen ref=%r id=%s", ref, cached["id"]
        )
        return await _channel_info_from_seen(client, cached)

    chat_type = getattr(chat, "type", "")
    if chat_type and chat_type not in ("channel", "supergroup", "group"):
        raise ChannelAccessError("این شناسه متعلق به یک کانال یا گروه نیست.")

    is_admin = False
    can_post = True
    try:
        me = await client.get_me()
        bot_id = getattr(me, "id", None)
        if bot_id:
            member = await client.get_chat_member(chat.id, bot_id)
            status = getattr(member, "status", "")
            if status == "creator":
                is_admin = True
                can_post = True
            elif status == "administrator":
                is_admin = True
                can_post = bool(getattr(member, "can_post_messages", True))
            else:
                is_admin = False
                can_post = False
    except Exception:
        is_admin = False
        can_post = False

    return ChannelInfo(
        telegram_id=chat.id,
        title=getattr(chat, "title", "بدون نام") or "بدون نام",
        username=getattr(chat, "username", None),
        is_admin=is_admin,
        can_post=can_post,
    )


async def _resolve_telethon(client: Any, ref: str | int) -> ChannelInfo:
    try:
        from telethon.tl.functions.channels import GetParticipantRequest
        from telethon.tl.types import Channel as TLChannel
        from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator, Chat
        from telethon.utils import get_peer_id

        entity = await client.get_entity(ref)
    except Exception as exc:
        raise ChannelAccessError(_not_found_message()) from exc

    if not isinstance(entity, (TLChannel, Chat)):
        raise ChannelAccessError("این شناسه متعلق به یک کانال یا گروه نیست.")

    is_admin = False
    can_post = True
    if isinstance(entity, TLChannel):
        try:
            me = await client.get_me()
            participant = await client(GetParticipantRequest(channel=entity, participant=me.id))
            is_admin = isinstance(
                participant.participant, (ChannelParticipantAdmin, ChannelParticipantCreator)
            )
            if isinstance(participant.participant, ChannelParticipantAdmin):
                rights = participant.participant.admin_rights
                can_post = bool(rights and rights.post_messages) or entity.megagroup
            elif isinstance(participant.participant, ChannelParticipantCreator):
                can_post = True
        except Exception:
            is_admin = False
            can_post = False

    return ChannelInfo(
        telegram_id=get_peer_id(entity),
        title=getattr(entity, "title", "بدون نام"),
        username=getattr(entity, "username", None),
        is_admin=is_admin,
        can_post=can_post,
    )


async def resolve_channel(client: Any, raw: str) -> ChannelInfo:
    raw = raw.strip()
    if _INVITE_RE.match(raw):
        raise ChannelAccessError(_INVITE_LINK_HINT)

    ref = normalize_channel_ref(raw)

    if not hasattr(client, "get_chat"):
        return await _resolve_telethon(client, ref)

    last_error: Exception | None = None
    candidates = _lookup_candidates(ref)
    for candidate in candidates:
        try:
            return await _resolve_bot_chat(client, candidate)
        except ChannelAccessError as exc:
            cause = exc.__cause__
            last_error = exc
            logger.info(
                "Channel lookup failed ref=%r candidate=%r: %s",
                raw,
                candidate,
                cause if cause is not None else exc,
            )
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            logger.warning("Channel lookup error ref=%r candidate=%r: %s", raw, candidate, exc)

    # Keep this at warning level: the handler replies to the admin and does not log the
    # underlying Bale/Telegram error, so this is the only trace of why it failed.
    logger.warning(
        "Channel resolution failed ref=%r platform=%s candidates=%s last_error=%s",
        raw,
        settings.platform,
        candidates,
        last_error,
    )
    raise ChannelAccessError(_not_found_message()) from last_error


async def verify_destination_permissions(client: Any, raw: str) -> ChannelInfo:
    info = await resolve_channel(client, raw)
    if not info.is_admin or not info.can_post:
        raise ChannelAccessError(
            "ربات باید در کانال مقصد Administrator باشد و دسترسی ارسال پیام داشته باشد."
        )
    return info
