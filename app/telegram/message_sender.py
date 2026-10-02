import logging
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import MessageIdInvalidError
from telethon.extensions import html as telethon_html
from telethon.tl.types import Message

from app.config import settings
from app.log_context import context, traced
from app.services import review_store
from app.services.ai_policy import AI_DROP_RESULT, AIProcessingError, AIReviewRequired
from app.services.ai_service import apply_ai_guardrails
from app.services.ai_settings import load_ai_settings
from app.services.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedMessage:
    html: str
    media: object | None
    forward_direct: bool = False


async def prepare_message(
    original: Message,
    source_id: int,
    signature: str | None,
    *,
    approved: bool = False,
    replacement_html: str | None = None,
) -> PreparedMessage | None:
    msg_id = getattr(original, "id", None)
    ai_enabled = load_ai_settings(settings).enabled

    if getattr(original, "poll", None):
        if ai_enabled and not approved:
            raise AIReviewRequired("poll")
        return PreparedMessage("", None, forward_direct=True)

    current_html = (
        replacement_html
        if replacement_html is not None
        else telethon_html.unparse(original.message or "", original.entities or [])
    )
    processed_html = (
        sanitize_text(current_html, remove_links=True)
        if approved
        else await apply_ai_guardrails(current_html, chat_id=source_id, message_id=msg_id)
    )
    if processed_html == AI_DROP_RESULT:
        return None
    if not ai_enabled:
        processed_html = sanitize_text(processed_html, remove_links=False)
    if signature:
        processed_html += ("\n\n" if processed_html.strip() else "") + signature
    if not processed_html and not original.media:
        return None
    media = original.media
    if media and type(media).__name__ == "MessageMediaWebPage":
        media = None
    return PreparedMessage(processed_html, media)


async def send_prepared_message(client, original, source_id, destination_id, prepared):
    if prepared.forward_direct:
        result = await client.forward_messages(
            entity=destination_id,
            messages=original.id,
            from_peer=source_id,
            drop_author=True,
        )
        return result[0] if isinstance(result, list) else result
    return await client.send_message(
        entity=destination_id,
        message=prepared.html,
        file=prepared.media,
        parse_mode="html",
        link_preview=False,
    )


@traced
async def send_message(
    client: TelegramClient,
    original: Message,
    source_id: int,
    destination_id: int,
    signature: str | None,
) -> Message | None:
    existing = review_store.find(source_id, getattr(original, "id", None), destination_id)
    if existing and existing.status in {"pending", "sending", "uncertain", "sent", "rejected"}:
        if existing.status == "rejected":
            return None
        raise AIReviewRequired("pending_admin_decision")
    try:
        prepared = await prepare_message(original, source_id, signature)
        if prepared is None:
            return None
        return await send_prepared_message(client, original, source_id, destination_id, prepared)
    except (AIReviewRequired, AIProcessingError) as exc:
        if getattr(original, "id", None) is not None:
            reason = str(exc) if isinstance(exc, AIReviewRequired) else "service_unavailable"
            review_store.enqueue(
                original, source_id, destination_id, context.get().get("job_id"), reason
            )
        raise


@traced
async def _send_message(
    client,
    original,
    source_id,
    destination_id,
    signature,
    *,
    approved=False,
    replacement_html=None,
):
    prepared = await prepare_message(
        original,
        source_id,
        signature,
        approved=approved,
        replacement_html=replacement_html,
    )
    if prepared is None:
        return None
    return await send_prepared_message(client, original, source_id, destination_id, prepared)


@traced
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
