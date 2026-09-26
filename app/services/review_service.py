import logging

from sqlalchemy import select

from app.config import settings
from app.database.database import get_session
from app.database.models import ForwardedMessage, ForwardJob, MessageStatus
from app.database.repository import ForwardedMessageRepository, SettingsRepository
from app.services import review_store
from app.telegram.forward_errors import ForwardErrorType, classify_error

logger = logging.getLogger(__name__)


def record_resolution(row, status, destination_message_id=None):
    if row.job_id is None:
        return
    with get_session() as session:
        old = session.scalar(
            select(ForwardedMessage).where(
                ForwardedMessage.source_channel_id == row.source_id,
                ForwardedMessage.source_message_id == row.message_id,
                ForwardedMessage.destination_channel_id == row.destination_id,
            )
        )
        job = session.get(ForwardJob, row.job_id)
        if not job:
            return
        if job and old and old.status == MessageStatus.FAILED and job.failed_messages > 0:
            job.failed_messages -= 1
            job.successful_messages += int(status == MessageStatus.SUCCESS)
            job.skipped_messages += int(status == MessageStatus.SKIPPED)
        ForwardedMessageRepository.record(
            session,
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
    if not row or row.fingerprint[:12] != version:
        return "این درخواست تغییر کرده است. /reviews را دوباره بزنید."
    if action == "reset":
        if review_store.reopen_uncertain(row.id, admin_id):
            logger.warning("Admin reopened uncertain send review_id=%d admin=%d", row.id, admin_id)
            return "درخواست دوباره آماده بررسی شد. فقط اگر پیام در مقصد نیست، تأییدش کنید. /reviews"
        return "این درخواست قابل بازگردانی نیست. /reviews"
    if action not in {"approve", "reject"}:
        return "عملیات نامعتبر است."
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
        sending = True
        sent = await _send_message(
            client, original, row.source_id, row.destination_id, signature, approved=True
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
