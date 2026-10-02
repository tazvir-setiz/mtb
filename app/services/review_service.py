import logging

from telethon.extensions import html

from app.config import settings
from app.database.database import get_session
from app.database.models import ForwardJob, MessageStatus
from app.database.repository import ForwardedMessageRepository, SettingsRepository
from app.services import review_drafts, review_store
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_settings import load_ai_settings
from app.services.fanout import clear_delivery_marker, deliver
from app.services.forward_results import record_result
from app.services.message_locks import message_lock
from app.services.review_rewriter import rewrite_draft
from app.telegram.forward_errors import ForwardErrorType, classify_error

logger = logging.getLogger(__name__)


def _record_route(
    job_id,
    row,
    destination_id,
    status,
    destination_message_id=None,
):
    if job_id is None:
        return
    with get_session() as session:
        if not session.get(ForwardJob, job_id):
            return
        if status != MessageStatus.SUCCESS and ForwardedMessageRepository.exists(
            session, row.source_id, row.message_id, destination_id
        ):
            return
    record_result(
        job_id,
        row.source_id,
        row.message_id,
        destination_id,
        status,
        destination_message_id=destination_message_id,
        error="رد شده توسط مدیر" if status == MessageStatus.SKIPPED else None,
    )


def record_resolution(row, status, destination_message_id=None):
    for destination_id, job_id in review_store.routes(row):
        _record_route(
            job_id,
            row,
            destination_id,
            status,
            destination_message_id,
        )


async def decide(review_id, version, action, admin_id, client):
    row = review_store.get(review_id)
    if not row:
        return "این درخواست وجود ندارد. /reviews"
    if row.status == "sending":
        return "این درخواست در حال ارسال است. /reviews"
    async with message_lock(row.source_id, row.message_id, None):
        return await _decide(review_id, version, action, admin_id, client)


async def _decide(review_id, version, action, admin_id, client):
    from app.telegram.message_sender import prepare_message, send_prepared_message

    if not settings.is_admin(admin_id):
        return "دسترسی غیرمجاز است."

    row = review_store.get(review_id)
    if not row or review_drafts.version(row) != version:
        return "این درخواست تغییر کرده است. /reviews را دوباره بزنید."

    routes = review_store.routes(row)

    if action == "reset":
        if review_store.reopen_uncertain(row.id, admin_id):
            for destination_id, _ in routes:
                clear_delivery_marker(row.source_id, row.message_id, destination_id)
            logger.warning(
                "Admin reopened uncertain send review_id=%d admin=%d",
                row.id,
                admin_id,
            )
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
        for destination_id, job_id in routes:
            _record_route(
                job_id,
                row,
                destination_id,
                MessageStatus.SKIPPED,
            )
        logger.info(
            "Review rejected review_id=%d admin=%d",
            row.id,
            admin_id,
        )
        return "⛔ پیام رد شد و به هیچ‌کدام از مقصدها ارسال نمی‌شود."

    sending = False
    try:
        messages = await client.get_messages(
            row.source_id,
            ids=[row.message_id],
        )
        if not messages or not messages[0]:
            review_store.set_status(row.id, "pending")
            return "پیام مبدأ حذف شده یا در دسترس نیست. می‌توانید آن را رد کنید. /reviews"

        original = messages[0]
        if review_store.content_fingerprint(original) != row.fingerprint:
            review_store.set_status(row.id, "changed")
            with get_session() as session:
                signature = SettingsRepository.get(session, "signature_text")
            try:
                await prepare_message(original, row.source_id, signature)
                reason = "content_changed"
            except AIReviewRequired as exc:
                reason = str(exc)
            except AIProcessingError:
                reason = "service_unavailable"
            review_store.enqueue_routes(original, row.source_id, routes, reason)
            return "متن یا رسانه تغییر کرده؛ ارسال نشد و Guard دوباره اجرا شد. اعلان تازه را بررسی کنید. /reviews"

        draft = review_drafts.get(row.id)
        if getattr(original, "poll", None) and (draft or action == "retry"):
            review_store.requeue(row.id, "poll")
            return (
                "ویرایش یا بازنویسی نظرسنجی پشتیبانی نمی‌شود؛ "
                "می‌توانید اصل نظرسنجی را تأیید یا رد کنید."
            )

        if action == "retry":
            candidate = (
                draft.text
                if draft
                else html.unparse(
                    original.message or "",
                    original.entities or [],
                )
            )
            candidate = await rewrite_draft(
                candidate,
                chat_id=row.source_id,
                message_id=row.message_id,
            )
            if candidate == "__DROP__":
                review_store.requeue(row.id, "ai_rejected")
                return (
                    "گارد پیشنهاد رد داد؛ هنوز ارسال نشده است. می‌توانید رد، تأیید یا ویرایش کنید."
                )
            review_drafts.save(
                row.id,
                version,
                candidate,
                "ai_draft",
                from_ai=True,
            )
            return "بازنگری آماده است؛ پس از مشاهده، تأیید، رد یا ویرایش کنید. هنوز ارسال نشده است."

        with get_session() as session:
            signature = SettingsRepository.get(
                session,
                "signature_text",
            )
            pending_routes = [
                (destination_id, job_id)
                for destination_id, job_id in routes
                if not ForwardedMessageRepository.exists(
                    session,
                    row.source_id,
                    row.message_id,
                    destination_id,
                )
            ]

        if not pending_routes:
            review_store.set_status(row.id, "sent")
            return "این پیام قبلاً به همه مقصدهای این درخواست ارسال شده است."

        prepared = await prepare_message(
            original,
            row.source_id,
            signature,
            approved=True,
            replacement_html=draft.text if draft else None,
        )
        if prepared is None:
            review_store.set_status(row.id, "rejected")
            for destination_id, job_id in pending_routes:
                _record_route(
                    job_id,
                    row,
                    destination_id,
                    MessageStatus.SKIPPED,
                )
            return "پیام پس از پاک‌سازی خالی بود؛ ارسال نشد."

        sending = True
        sent_count = 0
        first_destination_message_id = None
        failures = []

        for destination_id, job_id in pending_routes:
            try:
                status, destination_message_id = await deliver(
                    client,
                    original,
                    row.source_id,
                    destination_id,
                    job_id,
                    prepared,
                    send_prepared_message,
                )
                if first_destination_message_id is None:
                    first_destination_message_id = destination_message_id
                sent_count += int(status == MessageStatus.SUCCESS)
            except Exception as exc:
                error_type = classify_error(exc)
                logger.error(
                    "Review route send failed review_id=%d destination=%s type=%s reason=%s",
                    row.id,
                    destination_id,
                    type(exc).__name__,
                    error_type.value,
                )
                if error_type in {ForwardErrorType.UNKNOWN, ForwardErrorType.NETWORK_ERROR}:
                    review_store.set_status(
                        row.id,
                        "uncertain",
                        first_destination_message_id,
                    )
                    return (
                        "⚠️ نتیجه ارسال به یکی از مقصدها مشخص نیست؛ "
                        "برای جلوگیری از ارسال تکراری، اول مقصدها را بررسی کنید. "
                        "/reviews"
                    )
                failures.append((destination_id, error_type))

        if failures:
            review_store.set_status(
                row.id,
                "pending",
                first_destination_message_id,
            )
            return (
                f"⚠️ پیام به {sent_count} مقصد ارسال شد، اما "
                f"{len(failures)} مقصد ناموفق بود. "
                "برای مقصدهای ناموفق دوباره تأیید کنید."
            )

        review_store.set_status(
            row.id,
            "sent",
            first_destination_message_id,
        )
        logger.info(
            "Review resolved review_id=%d admin=%d destinations=%d",
            row.id,
            admin_id,
            sent_count,
        )
        return f"✅ پیام با تأیید شما به {sent_count} مقصد ارسال شد."

    except (AIReviewRequired, AIProcessingError) as exc:
        reason = (
            str(exc)
            if isinstance(exc, AIReviewRequired)
            else getattr(exc, "reason", "service_unavailable")
        )
        review_store.requeue(row.id, reason)
        return (
            "بازنویسی معتبر ساخته نشد؛ متن قبلی حفظ شد. "
            "دلیل در اعلان تازه آمده است؛ می‌توانید ویرایش یا رد کنید."
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
        review_store.set_status(
            row.id,
            "uncertain" if uncertain else "pending",
        )
        logger.error(
            "Review send failed review_id=%d type=%s uncertain=%s",
            row.id,
            type(exc).__name__,
            uncertain,
        )
        return (
            "⚠️ نتیجه ارسال مشخص نیست؛ برای جلوگیری از ارسال تکراری، "
            "اول مقصدها را بررسی کنید. /reviews"
            if uncertain
            else "⚠️ ارسال انجام نشد؛ دسترسی یا اتصال را بررسی و از /reviews دوباره تلاش کنید."
        )
