import logging

from telethon import TelegramClient
from telethon.errors import MessageIdInvalidError
from telethon.extensions import html as telethon_html
from telethon.tl.types import Message

from app.config import settings
from app.log_context import context, traced
from app.services import review_store
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_service import apply_ai_guardrails
from app.services.ai_settings import load_ai_settings
from app.services.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


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
        return await _send_message(client, original, source_id, destination_id, signature)
    except (AIReviewRequired, AIProcessingError) as exc:
        if getattr(original, "id", None) is not None:
            reason = str(exc) if isinstance(exc, AIReviewRequired) else "service_unavailable"
            review_store.enqueue(
                original, source_id, destination_id, context.get().get("job_id"), reason
            )
        raise


@traced
async def _send_message(client, original, source_id, destination_id, signature, *, approved=False):
    msg_id = getattr(original, "id", None)
    ai_enabled = load_ai_settings(settings).enabled
    logger.info(
        "پردازش پیام %s (مبدأ: %s → مقصد: %s، AI: %s)",
        msg_id,
        source_id,
        destination_id,
        "روشن" if ai_enabled else "خاموش",
    )

    if getattr(original, "poll", None):
        if ai_enabled and not approved:
            logger.info(
                "پیام %s نظرسنجی است و AI روشن است؛ فوروارد مستقیم مسدود شد (نیازمند بررسی).",
                msg_id,
            )
            raise AIReviewRequired("poll")
        logger.info("پیام %s نظرسنجی است. فوروارد مستقیم انجام می‌شود.", msg_id)
        result = await client.forward_messages(
            entity=destination_id,
            messages=original.id,
            from_peer=source_id,
            drop_author=True,
        )
        return result[0] if isinstance(result, list) else result

    current_html = telethon_html.unparse(original.message or "", original.entities or [])
    processed_html = (
        sanitize_text(current_html, remove_links=True)
        if approved
        else await apply_ai_guardrails(current_html, chat_id=source_id, message_id=msg_id)
    )
    if processed_html == "__DROP__":
        logger.info("پیام %s توسط AI Guardrails حذف شد؛ ارسال نمی‌شود.", msg_id)
        return None

    if not ai_enabled:
        processed_html = sanitize_text(processed_html, remove_links=False)

    if signature:
        separator = "\n\n" if processed_html.strip() else ""
        processed_html += separator + signature

    if not processed_html and not original.media:
        logger.info("پیام %s پس از پالایش خالی است و رسانه‌ای ندارد؛ ارسال نمی‌شود.", msg_id)
        return None

    media = original.media
    if media and type(media).__name__ == "MessageMediaWebPage":
        media = None

    logger.info(
        "ارسال پیام %s به مقصد %s (طول متن نهایی: %d)", msg_id, destination_id, len(processed_html)
    )
    sent = await client.send_message(
        entity=destination_id,
        message=processed_html,
        file=media,
        parse_mode="html",
        link_preview=False,
    )
    logger.info(
        "پیام %s با موفقیت به مقصد ارسال شد (شناسه مقصد: %s)", msg_id, getattr(sent, "id", None)
    )
    return sent


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
        logger.warning("پیام %s در کانال مبدأ یافت نشد یا حذف شده است.", msg_id)
        raise MessageIdInvalidError(request=None)
    return await send_message(client, messages[0], source_id, destination_id, signature)
