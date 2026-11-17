from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

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


def normalize_channel_ref(raw: str) -> str | int:
    raw = raw.strip()
    if raw.startswith("@"):
        return raw
    if raw.startswith("-100") or (raw.lstrip("-").isdigit()):
        try:
            return int(raw)
        except ValueError:
            pass
    if raw.startswith("https://t.me/c/"):
        parts = raw.split("https://t.me/c/")[-1].strip("/").split("/")
        if parts and parts[0].isdigit():
            return int(f"-100{parts[0]}")
    if raw.startswith("https://t.me/"):
        return "@" + raw.split("https://t.me/")[-1].strip("/")
    if raw.startswith("https://ble.ir/join/"):
        return raw
    if raw.startswith("https://ble.ir/"):
        part = raw.split("https://ble.ir/")[-1].strip("/").split("/")[0]
        if part:
            return f"@{part}"
    return raw if raw.startswith("@") else "@" + raw


async def resolve_channel(client: Any, raw: str) -> ChannelInfo:
    ref = normalize_channel_ref(raw)

    # Bot API client resolution
    if hasattr(client, "get_chat"):
        try:
            chat = await client.get_chat(ref)
        except Exception as exc:
            raise ChannelAccessError("کانال یافت نشد. شناسه یا Username را بررسی کنید.") from exc

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

    # Legacy Telethon fallback
    try:
        from telethon.tl.functions.channels import GetParticipantRequest
        from telethon.tl.types import Channel as TLChannel
        from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator, Chat
        from telethon.utils import get_peer_id

        entity = await client.get_entity(ref)
    except Exception as exc:
        raise ChannelAccessError("کانال یافت نشد. شناسه یا Username را بررسی کنید.") from exc

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


async def verify_destination_permissions(client: Any, raw: str) -> ChannelInfo:
    info = await resolve_channel(client, raw)
    if not info.is_admin or not info.can_post:
        raise ChannelAccessError(
            "ربات باید در کانال مقصد Administrator باشد و دسترسی ارسال پیام داشته باشد."
        )
    return info
