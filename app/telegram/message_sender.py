import logging

from telethon import TelegramClient
from telethon.errors import MessageIdInvalidError
from telethon.extensions import html as telethon_html
from telethon.tl.types import Message

from app.config import settings
from app.services.ai_policy import AIReviewRequired
from app.services.ai_service import apply_ai_guardrails
from app.services.ai_settings import load_ai_settings
from app.services.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


async def send_message(
    client: TelegramClient,
    original: Message,
    source_id: int,
    destination_id: int,
    signature: str | None,
) -> Message | None:
    msg_id = getattr(original, "id", None)
    ai_enabled = load_ai_settings(settings).enabled
    logger.debug(
        "پردازش پیام %s (مبدأ: %s → مقصد: %s، AI: %s)",
        msg_id,
        source_id,
        destination_id,
        "روشن" if ai_enabled else "خاموش",
    )

    if getattr(original, "poll", None):
        if ai_enabled:
            logger.info(
                "پیام %s نظرسنجی است و AI روشن است؛ فوروارد مستقیم مسدود شد (نیازمند بررسی).",
                msg_id,
            )
            raise AIReviewRequired(
                "Polls require review; text moderation cannot sanitize a forwarded poll"
            )
        logger.info("پیام %s نظرسنجی است. فوروارد مستقیم انجام می‌شود.", msg_id)
        result = await client.forward_messages(
            entity=destination_id,
            messages=original.id,
            from_peer=source_id,
            drop_author=True,
        )
        return result[0] if isinstance(result, list) else result

    current_html = telethon_html.unparse(original.message or "", original.entities or [])
    processed_html = await apply_ai_guardrails(current_html, chat_id=source_id, message_id=msg_id)
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

    logger.debug(
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
