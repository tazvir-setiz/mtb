import logging

from telethon.extensions import html

from app.config import settings
from app.database.database import get_session
from app.database.models import ForwardJob, MessageStatus
from app.database.repository import ForwardedMessageRepository, SettingsRepository
from app.services import review_drafts, review_store
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_settings import load_ai_settings
from app.services.forward_results import record_result
from app.services.review_rewriter import rewrite_draft
from app.telegram.forward_errors import ForwardErrorType, classify_error

logger = logging.getLogger(__name__)


def record_resolution(row, status, destination_message_id=None):
    if row.job_id is None:
        return
    with get_session() as session:
        if not session.get(ForwardJob, row.job_id):
            return
    record_result(
        row.job_id,
        row.source_id,
        row.message_id,
        row.destination_id,
        status,
        destination_message_id=destination_message_id,
        error="رد شده توسط مدیر" if status == MessageStatus.SKIPPED else None,
    )


async def decide(review_id, version, action, admin_id, client):
    from app.telegram.message_sender import _send_message

    if not settings.is_admin(admin_id):
        return "دسترسی غیرمجاز است."
    row = review_store.get(review_id)
    if not row or review_drafts.version(row) != version:
        return "این درخواست تغییر کرده است. /reviews را دوباره بزنید."
    if action == "reset":
        if review_store.reopen_uncertain(row.id, admin_id):
            logger.warning("Admin reopened uncertain send review_id=%d admin=%d", row.id, admin_id)
            return "درخواست دوباره آماده بررسی شد. فقط اگر پیام در مقصد نیست، تأییدش کنید. /reviews"
        return "این درخواست قابل بازگردانی نیست. /reviews"
    if action not in {"approve", "reject", "retry"}:
        return "عملیات نامعتبر است."
    if action == "retry" and not load_ai_settings().enabled:
        return "ابتدا AI را در تنظیمات روشن کنید؛ متن اصلی ارسال نشد."
    if not review_store.claim(review_id, admin_id):
        return "این درخواست قبلاً تعیین تکلیف شده یا در حال ارسال است. /reviews"
    if action == "reject":
        review_store.set_status(row.id, "rejected")
        record_resolution(row, MessageStatus.SKIPPED)
        logger.info("Review rejected review_id=%d admin=%d", row.id, admin_id)
        return "⛔ پیام رد شد و ارسال نمی‌شود."
    sending = False
    try:
        messages = await client.get_messages(row.source_id, ids=[row.message_id])
        if not messages or not messages[0]:
            review_store.set_status(row.id, "pending")
            return "پیام مبدأ حذف شده یا در دسترس نیست. می‌توانید آن را رد کنید. /reviews"
        original = messages[0]
        if review_store.content_fingerprint(original) != row.fingerprint:
            review_store.set_status(row.id, "changed")
            review_store.enqueue(
                original, row.source_id, row.destination_id, row.job_id, "content_changed"
            )
            return "متن یا رسانه تغییر کرده؛ ارسال نشد. اعلان تازه را بررسی کنید. /reviews"
        with get_session() as session:
            duplicate = ForwardedMessageRepository.exists(
                session, row.source_id, row.message_id, row.destination_id
            )
            signature = SettingsRepository.get(session, "signature_text")
        if duplicate:
            review_store.set_status(row.id, "sent", duplicate.destination_message_id)
            return "این پیام قبلاً به همین مقصد ارسال شده است."
        draft = review_drafts.get(row.id)
        if getattr(original, "poll", None) and (draft or action == "retry"):
            review_store.requeue(row.id, "poll")
            return "ویرایش یا بازنویسی نظرسنجی پشتیبانی نمی‌شود؛ می‌توانید اصل نظرسنجی را تأیید یا رد کنید."
        if action == "retry":
            candidate = (
                draft.text
                if draft
                else html.unparse(original.message or "", original.entities or [])
            )
            candidate = await rewrite_draft(
                candidate, chat_id=row.source_id, message_id=row.message_id
            )
            if candidate == "__DROP__":
                review_store.requeue(row.id, "ai_rejected")
                return (
                    "گارد پیشنهاد رد داد؛ هنوز ارسال نشده است. می‌توانید رد، تأیید یا ویرایش کنید."
                )
            review_drafts.save(row.id, version, candidate, "ai_draft", from_ai=True)
            return "بازنگری آماده است؛ پس از مشاهده، تأیید، رد یا ویرایش کنید. هنوز ارسال نشده است."
        sending = True
        sent = await _send_message(
            client,
            original,
            row.source_id,
            row.destination_id,
            signature,
            approved=action == "approve",
            replacement_html=draft.text if draft else None,
        )
        destination_message_id = getattr(sent, "id", None)
        review_store.set_status(row.id, "sent" if sent else "rejected", destination_message_id)
        record_resolution(
            row, MessageStatus.SUCCESS if sent else MessageStatus.SKIPPED, destination_message_id
        )
        logger.info(
            "Review resolved review_id=%d admin=%d destination_message=%s",
            row.id,
            admin_id,
            destination_message_id,
        )
        return (
            "✅ پیام با تأیید شما ارسال شد." if sent else "پیام پس از پاک‌سازی خالی بود؛ ارسال نشد."
        )
    except (AIReviewRequired, AIProcessingError) as exc:
        reason = (
            str(exc)
            if isinstance(exc, AIReviewRequired)
            else getattr(exc, "reason", "service_unavailable")
        )
        review_store.requeue(row.id, reason)
        return "بازنویسی معتبر ساخته نشد؛ متن قبلی حفظ شد. دلیل در اعلان تازه آمده است؛ می‌توانید ویرایش یا رد کنید."
    except Exception as exc:
        definite = classify_error(exc) in {
            ForwardErrorType.FLOOD_WAIT,
            ForwardErrorType.MESSAGE_NOT_FOUND,
            ForwardErrorType.PERMISSION_DENIED,
            ForwardErrorType.FORBIDDEN,
            ForwardErrorType.PROTECTED_CONTENT,
        }
        uncertain = sending and not definite
        review_store.set_status(row.id, "uncertain" if uncertain else "pending")
        logger.error(
            "Review send failed review_id=%d type=%s uncertain=%s",
            row.id,
            type(exc).__name__,
            uncertain,
        )
        return (
            "⚠️ نتیجه ارسال مشخص نیست؛ برای جلوگیری از ارسال تکراری، اول مقصد را بررسی کنید. /reviews"
            if uncertain
            else "⚠️ ارسال انجام نشد؛ دسترسی یا اتصال را بررسی و از /reviews دوباره تلاش کنید."
        )
