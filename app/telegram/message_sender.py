"""Shared message processing for manual transfers and the live listener."""

import logging

from telethon import TelegramClient
from telethon.errors import MessageIdInvalidError
from telethon.extensions import html as telethon_html
from telethon.tl.types import Message

from app.config import settings
from app.services.ai_policy import AIReviewRequired
from app.services.ai_service import apply_ai_guardrails
from app.services.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


async def send_message(
    client: TelegramClient,
    original: Message,
    source_id: int,
    destination_id: int,
    signature: str | None,
) -> Message | None:
    """Send a processed message, or return None when AI rejects it."""
    if getattr(original, "poll", None):
        if settings.ai_enabled:
            raise AIReviewRequired(
                "Polls require review; text moderation cannot sanitize a forwarded poll"
            )
        logger.info("Message %d is a poll. Forwarding directly.", original.id)
        result = await client.forward_messages(
            entity=destination_id,
            messages=original.id,
            from_peer=source_id,
            drop_author=True,
        )
        return result[0] if isinstance(result, list) else result

    current_html = telethon_html.unparse(original.message or "", original.entities or [])
    processed_html = await apply_ai_guardrails(current_html)
    if processed_html == "__DROP__":
        return None
    processed_html = sanitize_text(processed_html, remove_links=settings.ai_enabled)

    if signature:
        separator = "\n\n" if processed_html.strip() else ""
        processed_html += separator + signature

    if not processed_html and not original.media:
        return None

    media = original.media
    if media and type(media).__name__ == "MessageMediaWebPage":
        media = None

    return await client.send_message(
        entity=destination_id,
        message=processed_html,
        file=media,
        parse_mode="html",
        link_preview=False,
    )


async def fetch_and_send_message(
    client: TelegramClient,
    msg_id: int,
    source_id: int,
    destination_id: int,
    signature: str | None,
) -> Message | None:
    messages = await client.get_messages(source_id, ids=[msg_id])
    if not messages or not messages[0]:
        raise MessageIdInvalidError(request=None)
    return await send_message(client, messages[0], source_id, destination_id, signature)
