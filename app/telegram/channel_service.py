from __future__ import annotations

import logging
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import Channel as TLChannel
from telethon.tl.types import ChannelParticipantAdmin, ChannelParticipantCreator, Chat

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
    if raw.startswith("https://t.me/"):
        return "@" + raw.split("https://t.me/")[-1].strip("/")
    return raw if raw.startswith("@") else "@" + raw


async def resolve_channel(client: TelegramClient, raw: str) -> ChannelInfo:
    ref = normalize_channel_ref(raw)
    try:
        entity = await client.get_entity(ref)
    except (ValueError, UsernameNotOccupiedError) as exc:
        raise ChannelAccessError("کانال یافت نشد. شناسه یا Username را بررسی کنید.") from exc
    except ChannelPrivateError as exc:
        raise ChannelAccessError("این کانال خصوصی است و حساب متصل به ربات عضو آن نیست.") from exc

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
        except Exception:  # noqa: BLE001 - عضو نبودن یعنی عدم دسترسی
            is_admin = False
            can_post = False

    return ChannelInfo(
        telegram_id=entity.id if not isinstance(entity, TLChannel) else int(f"-100{entity.id}"),
        title=getattr(entity, "title", "بدون نام"),
        username=getattr(entity, "username", None),
        is_admin=is_admin,
        can_post=can_post,
    )


async def verify_destination_permissions(client: TelegramClient, raw: str) -> ChannelInfo:
    info = await resolve_channel(client, raw)
    if not info.is_admin or not info.can_post:
        raise ChannelAccessError(
            "ربات باید در کانال مقصد Administrator باشد و دسترسی ارسال پیام داشته باشد."
        )
    return info
