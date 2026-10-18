import asyncio
import json
import logging
import re
import time
from html import escape, unescape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, RetryAfter, TelegramError
from telethon.extensions import html

from app.config import settings
from app.handlers import review_edit
from app.handlers.auth import is_authorized, reject
from app.services import review_drafts, review_store
from app.services.review_kind import ReviewKind, parse_review_reason
from app.services.review_service import decide
from app.telegram.client import ensure_started

logger = logging.getLogger(__name__)
GUARD_BLOCK_REASONS = {
    "abuse": "گارد پیام را توهین مستقیم تشخیص داده است",
    "pure_abuse": "پیام حاوی فحاشی و توهین مستقیم است",
    "hate": "گارد پیام را حمله یا نفرت‌پراکنی تشخیص داده است",
    "threat": "گارد پیام را تهدید تشخیص داده است",
    "porn": "گارد پیام را محتوای جنسی صریح تشخیص داده است",
    "spam": "گارد پیام را اسپم یا تبلیغ ممنوع تشخیص داده است",
    "injection": "گارد پیام را تلاش برای دورزدن یا نفوذ به دستورها تشخیص داده است",
    "off_topic": "پیام خارج از موضوعات تعیین‌شده در فیلتر موضوعی است",
    "policy_violation": "نقض قوانین و سیاست‌های محتوایی",
}

REASONS = {
    # Guard / Policy Categories
    "spam": "گارد پیام را اسپم یا تبلیغاتی تشخیص داده است",
    "abuse": "گارد پیام را حاوی توهین تشخیص داده است",
    "pure_abuse": "پیام حاوی فحاشی و توهین مستقیم و بدون محتوای مفید است",
    "hate": "گارد پیام را حاوی حمله یا نفرت‌پراکنی تشخیص داده است",
    "threat": "گارد پیام را حاوی تهدید تشخیص داده است",
    "porn": "گارد پیام را حاوی محتوای نامناسب جنسی تشخیص داده است",
    "injection": "گارد در پیام تلاش برای دورزدن قوانین یا نفوذ به دستورها تشخیص داده است",
    "off_topic": "پیام مرتبط با موضوعات تعیین‌شده در فیلتر موضوعی نیست",
    "political": "پس از بازنگری خودکار، مدل همچنان پیام را موضع‌گیری یا تبلیغ سیاسی تشخیص داده است",
    "policy_violation": "نقض قوانین و سیاست‌های محتوایی",

    # AI Reasoning & Semantic Pipeline Verdicts
    "ambiguous_meaning": "مفهوم یا ادعای پیام مبهم و دوپهلو است و مدل نتوانست با اطمینان آن را تأیید کند",
    "no_protected_meaning": "پیام فاقد محتوای مفید یا مستقل برای بازنویسی و انتشار است",
    "grounding_unresolved": "پیام حاوی ادعای خبری یا فکت نامشخص است و راستی‌آزمایی آن انجام نشد",
    "conflicting_drop_decisions": "مراحل مختلف گارد درباره دلیل حذف پیام به توافق نرسیدند",
    "conflicting_decisions": "مراحل گارد درباره دلیل حذف توافق ندارند",
    "missing_evidence": "مدل برای حذف پیام شاهد معتبر یا دلیل کافی ارائه نکرد",
    "meaning_changed": "بازنویسی معنی یا اطلاعات اصلی را تغییر داده است",
    "invalid_verification": "پاسخ مرحلهٔ بررسی نهایی معتبر نبود",
    "policy_mismatch": "پاسخ مدل با حساسیت‌های انتخاب‌شده سازگار نیست",
    "rewrite_failed": "بازنویسی خودکار نتوانست از بررسی نهایی قوانین عبور کند",
    "failed_rewrite_verification": "نسخهٔ بازنویسی‌شده از بررسی نهایی انطباق با قوانین عبور نکرد",
    "low_confidence": "اطمینان مدل کافی نیست",
    "review": "مدل درباره محتوای پیام مطمئن نیست",

    # Draft & Review State
    "ai_draft": "پیش‌نویس بازنگری AI آمادهٔ تصمیم شماست؛ هنوز ارسال نشده",
    "manual_draft": "ویرایش شما ذخیره شد؛ برای ارسال تأیید کنید",
    "ai_rejected": "AI پیشنهاد رد داده؛ تصمیم نهایی با شماست",
    "pending_admin_decision": "پیام مشابه در انتظار تصمیم‌گیری مدیر در صف بررسی است",
    "content_changed": "محتوای پیام پس از درخواست قبلی تغییر کرده است",
    "poll": "نظرسنجی نیاز به بررسی و تأیید مدیر دارد",
    "unchecked_media": "رسانه یا فایل پیوست نیاز به بررسی و تأیید مدیر دارد",

    # System & Transport Status
    "send_uncertain": "نتیجهٔ ارسال مشخص نیست؛ پیش از تلاش مجدد مقصدها را بررسی کنید",
    "budget_exhausted": "سقف زمان یا مراحل بررسی تمام شد؛ ارسال انجام نشد",
    "timeout": "مهلت پاسخ AI تمام شد؛ می‌توانید بررسی با AI را دوباره اجرا کنید",
    "response_truncated": "پاسخ مدل به سقف توکن رسید و ناقص ماند",
    "provider_refusal": "سرویس AI از پاسخ‌دهی به این پیام خودداری کرد",
    "invalid_output": "قالب پاسخ مدل معتبر نبود",
    "missing_api_key": "کلید API سرویس AI تنظیم نشده است",
    "invalid_credentials": "سرویس AI کلید یا دسترسی حساب را نپذیرفت",
    "rate_limit": "محدودیت درخواست یا اتمام اعتبار سرویس AI",
    "bad_request": "پارامترها یا درخواست ارسالی به AI پذیرفته نشد",
    "provider_error": "خطای سرویس‌دهنده هوش مصنوعی (HTTP Error)",
    "connection_error": "اتصال به سرویس هوش مصنوعی برقرار نشد",
    "service_unavailable": "سرویس AI در دسترس نیست یا پاسخ معتبر نداد",
    "circuit_open": "سرویس AI موقتاً در دوره توقف پس از خطاست",
    "input_too_long": "طول پیام بیش از سقف بررسی خودکار است",
    "unsafe_output": "خروجی پردازش‌شده حاوی لینک یا محتوای ناامن است",
    "ai_disabled": "بررسی هوش مصنوعی در تنظیمات غیرفعال است",
    "invalid_meaning": "خطا در استخراج معنای پیام توسط مدل",
    "invalid_rewrite": "خطا در تولید بازنویسی توسط مدل",
    "invalid_judge": "خطا در داوری انطباق متن توسط مدل",
    "unknown_stage": "مرحله پردازش نامعتبر در گارد",
    "AI decision requires review": "پالایش پیام توسط هوش مصنوعی نیاز به بررسی و تأیید مدیر دارد",
}


def escaped_preview(value):
    parts = []
    size = 0
    for character in value:
        part = escape(character)
        size += len(part.encode("utf-16-le")) // 2
        if size > 2300:
            parts.append("…")
            break
        parts.append(part)
    return "".join(parts)


def guard_block_reason(parsed):
    code = (parsed.guard_label or parsed.reason or "unknown").strip().lower()
    detail = GUARD_BLOCK_REASONS.get(code) or REASONS.get(code)
    if not detail:
        if any("\u0600" <= c <= "\u06ff" for c in code):
            detail = code
        else:
            detail = "گارد این پیام را برای انتشار نامناسب تشخیص داده است"

    extra = (parsed.reason or "").strip()
    if extra and extra.lower() not in {code, (parsed.guard_label or "").strip().lower()}:
        extra_desc = REASONS.get(extra.lower(), extra)
        return f"{detail} — دلیل: {extra_desc}"
    return detail


def get_row_reason(row):
    """استخراج و قالب‌بندی دلیل نیاز به بررسی برای نمایش در کارت و فهرست."""
    raw = (getattr(row, "reason", None) or "").strip()
    if not raw:
        return "محتوا نیاز به تصمیم مدیر دارد"

    parsed = parse_review_reason(raw)
    if parsed.kind is ReviewKind.GUARD_BLOCK:
        return guard_block_reason(parsed)

    # 1. Direct match in REASONS or GUARD_BLOCK_REASONS
    if raw in REASONS:
        return REASONS[raw]
    raw_lower = raw.lower()
    if raw_lower in REASONS:
        return REASONS[raw_lower]
    if raw_lower in GUARD_BLOCK_REASONS:
        return GUARD_BLOCK_REASONS[raw_lower]

    # 2. Key-detail match if raw contains separator (e.g. "low_confidence:detail" or "review:detail")
    if ":" in raw:
        base, _, detail = raw.partition(":")
        base_lower = base.strip().lower()
        detail = detail.strip()
        matched = REASONS.get(base_lower) or GUARD_BLOCK_REASONS.get(base_lower)
        if matched:
            detail_desc = REASONS.get(detail.lower(), detail)
            return f"{matched} — جزئیات: {detail_desc}" if detail else matched

    # 3. If raw already contains meaningful Persian text
    if any("\u0600" <= c <= "\u06ff" for c in raw):
        return raw

    # 4. If raw is an English identifier/phrase, display it informatively instead of a generic fallback
    return f"نیاز به بررسی مدیر — ({raw})"


def list_preview(text, max_len=75):
    """تولید یک خلاصه کوتاه تک‌خطی و ایمن‌شده برای نمایش در فهرست بازبینی."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return "[بدون متن]"
    if len(cleaned) > max_len:
        return escape(cleaned[: max_len - 1]) + "…"
    return escape(cleaned)


def build_pending_list(rows, after_id=0):
    """ساخت پیام فهرست شماره‌دار پیام‌های معلق به همراه دکمه‌های شیشه‌ای انتخاب هر مورد."""
    header = "📋 <b>فهرست پیام‌های نیازمند بررسی:</b>\n\n"
    items = []
    for idx, row in enumerate(rows, 1):
        parsed = parse_review_reason(row.reason)
        blocked = parsed.kind is ReviewKind.GUARD_BLOCK
        icon = "🚫" if blocked else "⚠️"
        reason = escape(get_row_reason(row))
        content = list_preview(row.preview)
        items.append(
            f"<b>{idx}. پیام #{row.id}</b>\n"
            f"   {icon} <b>علت:</b> {reason}\n"
            f"   📝 <b>محتوا:</b> <i>{content}</i>"
        )
    footer = "\n\n<i>برای مشاهده پیام کامل و اقدام (تأیید، ویرایش، رد)، روی دکمه شماره پیام کلیک کنید:</i>"
    text = header + "\n\n".join(items) + footer

    # ایجاد دکمه‌های شیشه‌ای به صورت دو دکمه در هر سطر
    buttons = []
    row_buttons = []
    for idx, row in enumerate(rows, 1):
        row_buttons.append(
            InlineKeyboardButton(f"🔍 {idx}. پیام #{row.id}", callback_data=f"review:show:{row.id}")
        )
        if len(row_buttons) == 2:
            buttons.append(row_buttons)
            row_buttons = []
    if row_buttons:
        buttons.append(row_buttons)

    # دکمه‌های ناوبری، به‌روزرسانی و صفحه بعد
    nav_row = []
    if after_id > 0:
        nav_row.append(InlineKeyboardButton("⏮ صفحه اول", callback_data="review:list:0"))
    nav_row.append(InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"review:list:{after_id}"))
    if len(rows) == 10:
        nav_row.append(InlineKeyboardButton("موارد بعدی ➡️", callback_data=f"review:list:{rows[-1].id}"))
    if nav_row:
        buttons.append(nav_row)

    return text, InlineKeyboardMarkup(buttons)


def card(row):
    parsed = parse_review_reason(row.reason)
    blocked = parsed.kind is ReviewKind.GUARD_BLOCK
    reason = escape(get_row_reason(row))
    route_count = len(review_store.routes(row))
    destination_line = (
        f"مقصد: {row.destination_id}" if route_count == 1 else f"مقصدها: {route_count} کانال"
    )
    if blocked:
        text = (
            f"🚫 <b>پیام توسط گارد مسدود شد</b> — #{row.id}\n"
            f"مبدأ: {row.source_id} — پیام: {row.message_id}\n"
            f"{destination_line}\n"
            f"تشخیص گارد: {reason}\n"
            "تصمیم گارد: <b>DROP</b>"
        )
    else:
        text = (
            f"🔎 بررسی پیام #{row.id}\n"
            f"مبدأ: {row.source_id} — پیام: {row.message_id}\n"
            f"{destination_line}\n"
            f"دلیل: {reason}"
        )
    buttons = []
    if row.status == "pending":
        suffix = f"{row.id}:{review_drafts.version(row)}"
        rewrite_label = "🤖 ساخت نسخهٔ قابل انتشار" if blocked else "🤖 بازنویسی با AI"
        approve_label = "⚠️ ارسال با تأیید مدیر" if blocked else "✅ تأیید نسخهٔ فعلی"
        reject_label = "🗑 رد نهایی" if blocked else "⛔ رد پیام"
        buttons.append(
            [InlineKeyboardButton(rewrite_label, callback_data=f"review:retry:{suffix}")]
        )
        buttons.append(
            [
                InlineKeyboardButton(approve_label, callback_data=f"review:approve:{suffix}"),
                InlineKeyboardButton("✏️ ویرایش دستی" if blocked else "✏️ ویرایش", callback_data=f"review:edit:{suffix}"),
                InlineKeyboardButton(reject_label, callback_data=f"review:reject:{suffix}"),
            ]
        )
        buttons.append(
            [InlineKeyboardButton("👁 مشاهده متن پیام", callback_data=f"review:preview:{suffix}")]
        )
    else:
        text += "\n⚠️ ارسال در جریان است یا نتیجه‌اش مشخص نیست. پیش از هر اقدام مقصد را بررسی کنید."
        if row.status == "uncertain":
            buttons.append(
                [
                    InlineKeyboardButton(
                        "مقصد را بررسی کردم؛ بازگشت به صف",
                        callback_data=f"review:reset:{row.id}:{review_drafts.version(row)}",
                    )
                ]
            )
    source = str(row.source_id)
    if source.startswith("-100"):
        buttons.append(
            [
                InlineKeyboardButton(
                    "مشاهده پیام اصلی و رسانه", url=f"https://t.me/c/{source[4:]}/{row.message_id}"
                )
            ]
        )
    return text, InlineKeyboardMarkup(buttons)


def _plain_card(text):
    """Remove presentation markup before retrying a rejected HTML card."""
    return unescape(re.sub(r"<[^>]*>", "", text))


async def send_card(bot, admin_id, row):
    draft = review_drafts.get(row.id)
    text, markup = card(row)
    version = review_drafts.version(row, draft)
    if draft:
        plain, _ = html.parse(draft.text)
        for start in range(0, len(plain), 1500):
            await bot.send_message(
                chat_id=admin_id,
                text="متن کامل پیش‌نویس:\n" + plain[start : start + 1500],
                parse_mode=None,
                disable_web_page_preview=True,
            )
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=markup,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except BadRequest:
        # A malformed entity or button must not hide a review from the admin.
        await bot.send_message(
            chat_id=admin_id,
            text=_plain_card(text),
            parse_mode=None,
            disable_web_page_preview=True,
        )
    return version


async def notify_pending(bot):
    after_id = 0
    unreachable_admins: dict[int, tuple[float, int]] = {}
    while True:
        try:
            now = time.monotonic()
            rows = review_store.pending(after_id=after_id)
            for row in rows:
                after_id = row.id
                if row.status == "sending":
                    continue
                for admin_id in settings.admin_ids:
                    last_attempt, failures = unreachable_admins.get(admin_id, (0.0, 0))
                    if failures > 0:
                        backoff = min(3600.0, 60.0 * (2 ** min(failures - 1, 6)))
                        if now - last_attempt < backoff:
                            continue
                    if admin_id in json.loads(row.notified):
                        continue
                    try:
                        version = await send_card(bot, admin_id, row)
                        unreachable_admins.pop(admin_id, None)
                        review_store.mark_notified(
                            row.id, admin_id, row.fingerprint, row.status, version
                        )
                    except RetryAfter as exc:
                        delay = exc.retry_after
                        await asyncio.sleep(
                            delay.total_seconds() if hasattr(delay, "total_seconds") else delay
                        )
                    except Exception as exc:
                        detail = str(exc)
                        if "chat not found" in detail.lower() or "blocked" in detail.lower():
                            prev_time, prev_fail = unreachable_admins.get(admin_id, (0.0, 0))
                            unreachable_admins[admin_id] = (now, prev_fail + 1)
                        logger.warning(
                            "Review notification failed review_id=%d admin=%s type=%s detail=%s; available via /reviews",
                            row.id,
                            admin_id,
                            type(exc).__name__,
                            detail[:300],
                        )
                    await asyncio.sleep(1.1)
            if not rows:
                after_id = 0
        except Exception as exc:
            logger.error("Review notification worker failed type=%s", type(exc).__name__)
        await asyncio.sleep(5)


async def show_pending(update, context, after_id=0):
    if not is_authorized(update):
        await reject(update)
        return
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "برای بررسی پیام‌ها، /reviews را در چت خصوصی ربات بفرستید."
        )
        return
    rows = review_store.pending(limit=10, after_id=after_id)
    query = getattr(update, "callback_query", None)
    if not rows:
        msg = (
            "پیام دیگری برای بررسی وجود ندارد."
            if after_id > 0
            else "هیچ پیامی در صف بررسی وجود ندارد."
        )
        if query and hasattr(query, "answer"):
            try:
                await query.answer(msg, show_alert=True)
                return
            except TelegramError:
                pass
        await update.effective_message.reply_text(msg)
        return

    text, markup = build_pending_list(rows, after_id)
    if query and getattr(query, "message", None) and hasattr(query, "edit_message_text"):
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            return
        except TelegramError:
            pass

    await update.effective_message.reply_text(
        text=text,
        reply_markup=markup,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def on_callback(update, context):
    if not is_authorized(update):
        await reject(update)
        return
    query = update.callback_query
    await query.answer()
    if update.effective_chat.type != "private":
        return
    parts = (query.data or "").split(":")
    if len(parts) == 3 and parts[1] == "list" and parts[2].isdigit():
        await show_pending(update, context, int(parts[2]))
        return
    if len(parts) == 3 and parts[1] == "show" and parts[2].isdigit():
        row = review_store.get(int(parts[2]))
        if not row:
            await update.effective_message.reply_text(
                "این پیام یافت نشد یا قبلاً تعیین تکلیف شده است."
            )
            return
        if row.status not in {"pending", "uncertain"}:
            await update.effective_message.reply_text(
                f"این پیام قبلاً تعیین تکلیف شده است (وضعیت: {row.status})."
            )
            return
        await send_card(context.bot, update.effective_user.id, row)
        return
    if len(parts) >= 3 and parts[1] == "preview" and parts[2].isdigit():
        row = review_store.get(int(parts[2]))
        if row:
            preview_text = (row.preview or "[پیام بدون متن]").strip()
            await update.effective_message.reply_text(
                f"📝 <b>متن پیام #{row.id}:</b>\n\n{escape(preview_text)}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        return
    if (
        len(parts) != 4
        or parts[1] not in {"approve", "reject", "reset", "retry", "edit"}
        or not parts[2].isdigit()
    ):
        return
    if parts[1] == "edit":
        row = review_store.get(int(parts[2]))
        if row:
            await review_edit.begin(update, context, row, parts[3])
        return
    try:
        client = await ensure_started() if parts[1] in {"approve", "retry"} else None
    except Exception as exc:
        logger.warning("Review Telegram connection failed type=%s", type(exc).__name__)
        await update.effective_message.reply_text(
            "اتصال تلگرام برقرار نشد. درخواست ذخیره شده؛ دوباره تلاش کنید."
        )
        return
    result = await decide(int(parts[2]), parts[3], parts[1], update.effective_user.id, client)
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    await update.effective_message.reply_text(result)
    row = review_store.get(int(parts[2]))
    if row and row.status == "pending":
        version = await send_card(context.bot, update.effective_user.id, row)
        review_store.mark_notified(
            row.id, update.effective_user.id, row.fingerprint, row.status, version
        )
