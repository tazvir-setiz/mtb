import asyncio
import json
import logging
import re
import time
from collections import Counter
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
from app.telegram.callback_ack import ack
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

    buttons.append([InlineKeyboardButton("🏠 بازگشت به داشبورد", callback_data="nav:home")])

    return text, InlineKeyboardMarkup(buttons)


def card(
    row,
    note: str | None = None,
    show_preview: bool = False,
    in_list: bool = False,
):
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

    draft = review_drafts.get(row.id)

    if note:
        text += f"\n\n💡 <b>وضعیت اقدام:</b> <i>{escape(note)}</i>"

    if draft and getattr(draft, "text", None):
        plain_draft = draft.text.strip()
        text += (
            f"\n\n📝 <b>پیش‌نویس بازنویسی AI (آماده تأیید):</b>\n"
            f"<blockquote>{escape(plain_draft[:1500])}</blockquote>"
        )

    if show_preview:
        preview_text = (row.preview or "[پیام بدون متن]").strip()
        text += (
            f"\n\n📄 <b>متن اصلی پیام:</b>\n"
            f"<blockquote>{escape(preview_text[:1500])}</blockquote>"
        )

    buttons = []
    if row.status == "pending":
        suffix = f"{row.id}:{review_drafts.version(row, draft)}"
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
        if show_preview:
            buttons.append(
                [InlineKeyboardButton("🙈 بستن متن پیام", callback_data=f"review:hide_preview:{suffix}")]
            )
        else:
            buttons.append(
                [InlineKeyboardButton("👁 مشاهده متن پیام", callback_data=f"review:preview:{suffix}")]
            )
        if in_list:
            buttons.append(
                [InlineKeyboardButton("📋 بازگشت به فهرست", callback_data="review:list:0")]
            )
    else:
        text += "\n\n⚠️ ارسال در جریان است یا نتیجه‌اش مشخص نیست. پیش از هر اقدام مقصد را بررسی کنید."
        if row.status == "uncertain":
            buttons.append(
                [
                    InlineKeyboardButton(
                        "مقصد را بررسی کردم؛ بازگشت به صف",
                        callback_data=f"review:reset:{row.id}:{review_drafts.version(row, draft)}",
                    )
                ]
            )
        if in_list:
            buttons.append(
                [InlineKeyboardButton("📋 بازگشت به فهرست", callback_data="review:list:0")]
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


SYSTEMIC_AI_REASONS = {
    "missing_api_key",
    "invalid_credentials",
    "rate_limit",
    "circuit_open",
    "service_unavailable",
    "connection_error",
    "provider_error",
    "timeout",
}


def _is_systemic_ai_error(reason: str) -> bool:
    parsed = parse_review_reason(reason)
    base = parsed.reason.strip().lower()
    return base in SYSTEMIC_AI_REASONS


async def send_systemic_alert(
    bot, admin_id: int, reason_code: str, count: int, total_pending: int
) -> None:
    reason_desc = REASONS.get(reason_code, reason_code)
    text = (
        "⚠️ <b>هشدار خطای سراسری هوش مصنوعی</b>\n\n"
        f"• <b>علت:</b> {reason_desc}\n"
        f"• <b>پیام‌های تحت تأثیر:</b> {count} پیام به صف بازبینی منتقل شدند\n"
        f"• <b>کل صف بازبینی:</b> {total_pending} پیام\n\n"
        "<i>پیام‌های ورودی بدون بازنویسی در صف ذخیره می‌شوند تا مشکل کلید یا سرویس برطرف شود.</i>"
    )
    buttons = [
        [InlineKeyboardButton("⚙️ تنظیمات هوش مصنوعی", callback_data="settings:ai")],
        [InlineKeyboardButton(f"🔎 صف بازبینی ({total_pending})", callback_data="review:list:0")],
        [InlineKeyboardButton("🏠 داشبورد", callback_data="nav:home")],
    ]
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except BadRequest:
        await bot.send_message(
            chat_id=admin_id,
            text=_plain_card(text),
            parse_mode=None,
            disable_web_page_preview=True,
        )


async def send_batch_notification(
    bot, admin_id: int, rows: list, total_pending: int
) -> None:
    reasons_count: Counter = Counter()
    for r in rows:
        reasons_count[get_row_reason(r)] += 1
    top_reason = reasons_count.most_common(1)[0][0] if reasons_count else "بررسی محتوا"

    text = (
        f"📬 <b>{len(rows)} پیام جدید در صف بازبینی قرار گرفت</b>\n\n"
        f"• <b>علت عمده:</b> {top_reason}\n"
        f"• <b>مجموع پیام‌های در انتظار:</b> {total_pending} پیام\n\n"
        "<i>برای جلوگیری از شلوغ شدن چت، اعلان‌ها تجمیع شدند. با لمس دکمه زیر پیام‌ها را بررسی کنید:</i>"
    )
    buttons = [
        [
            InlineKeyboardButton(
                f"🔎 مشاهده صف بازبینی ({total_pending} پیام)", callback_data="review:list:0"
            )
        ],
        [InlineKeyboardButton("🏠 بازگشت به داشبورد", callback_data="nav:home")],
    ]
    try:
        await bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except BadRequest:
        await bot.send_message(
            chat_id=admin_id,
            text=_plain_card(text),
            parse_mode=None,
            disable_web_page_preview=True,
        )


async def send_card(bot, admin_id, row):
    draft = review_drafts.get(row.id)
    text, markup = card(row)
    version = review_drafts.version(row, draft)
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
    last_systemic_alert: dict[tuple[int, str], float] = {}

    while True:
        try:
            now = time.monotonic()
            rows = review_store.pending(after_id=after_id)
            if rows:
                after_id = max(r.id for r in rows)

                for admin_id in settings.admin_ids:
                    last_attempt, failures = unreachable_admins.get(admin_id, (0.0, 0))
                    if failures > 0:
                        backoff = min(3600.0, 60.0 * (2 ** min(failures - 1, 6)))
                        if now - last_attempt < backoff:
                            continue

                    unnotified = [
                        r
                        for r in rows
                        if r.status != "sending" and admin_id not in json.loads(r.notified)
                    ]
                    if not unnotified:
                        continue

                    systemic_rows = [r for r in unnotified if _is_systemic_ai_error(r.reason)]
                    non_systemic_rows = [
                        r for r in unnotified if not _is_systemic_ai_error(r.reason)
                    ]

                    # 1. Handle systemic AI error rows with deduplication / cooldown
                    if systemic_rows:
                        by_code: dict[str, list] = {}
                        for r in systemic_rows:
                            code = parse_review_reason(r.reason).reason.strip().lower()
                            by_code.setdefault(code, []).append(r)

                        for code, code_rows in by_code.items():
                            last_time = last_systemic_alert.get((admin_id, code), 0.0)
                            if now - last_time >= 600.0:
                                try:
                                    await send_systemic_alert(
                                        bot, admin_id, code, len(code_rows), len(rows)
                                    )
                                    last_systemic_alert[(admin_id, code)] = now
                                    unreachable_admins.pop(admin_id, None)
                                except RetryAfter as exc:
                                    delay = exc.retry_after
                                    await asyncio.sleep(
                                        delay.total_seconds()
                                        if hasattr(delay, "total_seconds")
                                        else delay
                                    )
                                    continue
                                except Exception as exc:
                                    detail = str(exc)
                                    if "chat not found" in detail.lower() or "blocked" in detail.lower():
                                        prev_time, prev_fail = unreachable_admins.get(
                                            admin_id, (0.0, 0)
                                        )
                                        unreachable_admins[admin_id] = (now, prev_fail + 1)
                                    logger.warning("Systemic alert failed for admin=%s: %s", admin_id, exc)
                                    continue

                            for r in code_rows:
                                draft = review_drafts.get(r.id)
                                v = review_drafts.version(r, draft)
                                review_store.mark_notified(
                                    r.id, admin_id, r.fingerprint, r.status, v
                                )

                    # 2. Handle non-systemic content reviews
                    if len(non_systemic_rows) > 2:
                        try:
                            await send_batch_notification(
                                bot, admin_id, non_systemic_rows, len(rows)
                            )
                            unreachable_admins.pop(admin_id, None)
                            for r in non_systemic_rows:
                                draft = review_drafts.get(r.id)
                                v = review_drafts.version(r, draft)
                                review_store.mark_notified(
                                    r.id, admin_id, r.fingerprint, r.status, v
                                )
                        except RetryAfter as exc:
                            delay = exc.retry_after
                            await asyncio.sleep(
                                delay.total_seconds()
                                if hasattr(delay, "total_seconds")
                                else delay
                            )
                        except Exception as exc:
                            detail = str(exc)
                            if "chat not found" in detail.lower() or "blocked" in detail.lower():
                                prev_time, prev_fail = unreachable_admins.get(admin_id, (0.0, 0))
                                unreachable_admins[admin_id] = (now, prev_fail + 1)
                            logger.warning("Batch notification failed for admin=%s: %s", admin_id, exc)
                    else:
                        for r in non_systemic_rows:
                            try:
                                v = await send_card(bot, admin_id, r)
                                unreachable_admins.pop(admin_id, None)
                                review_store.mark_notified(
                                    r.id, admin_id, r.fingerprint, r.status, v
                                )
                            except RetryAfter as exc:
                                delay = exc.retry_after
                                await asyncio.sleep(
                                    delay.total_seconds()
                                    if hasattr(delay, "total_seconds")
                                    else delay
                                )
                            except Exception as exc:
                                detail = str(exc)
                                if "chat not found" in detail.lower() or "blocked" in detail.lower():
                                    prev_time, prev_fail = unreachable_admins.get(
                                        admin_id, (0.0, 0)
                                    )
                                    unreachable_admins[admin_id] = (now, prev_fail + 1)
                                logger.warning(
                                    "Review notification failed review_id=%d admin=%s type=%s detail=%s; available via /reviews",
                                    r.id,
                                    admin_id,
                                    type(exc).__name__,
                                    detail[:300],
                                )
                            await asyncio.sleep(1.1)
            else:
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
        if query and await ack(query, msg, show_alert=True):
            return
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
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
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
    await ack(query)
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
        if query and getattr(query, "message", None) and hasattr(query, "edit_message_text"):
            text, markup = card(row, in_list=True)
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
            except TelegramError:
                pass
        await send_card(context.bot, update.effective_user.id, row)
        return

    if parts[1] == "hide_preview" and len(parts) >= 3 and parts[2].isdigit():
        row = review_store.get(int(parts[2]))
        if row and query and getattr(query, "message", None) and hasattr(query, "edit_message_text"):
            text, markup = card(row, show_preview=False, in_list=True)
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
            except TelegramError:
                pass
        return

    if len(parts) >= 3 and parts[1] == "preview" and parts[2].isdigit():
        row = review_store.get(int(parts[2]))
        if row:
            if query and getattr(query, "message", None) and hasattr(query, "edit_message_text"):
                text, markup = card(row, show_preview=True, in_list=True)
                try:
                    await query.edit_message_text(
                        text=text,
                        reply_markup=markup,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    return
                except BadRequest as exc:
                    if "not modified" in str(exc).lower():
                        return
                except TelegramError:
                    pass
            # Fallback for unit tests where query.message or edit_message_text is absent:
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
    row = review_store.get(int(parts[2]))

    # In-place update for interactive callbacks:
    can_edit = bool(query and getattr(query, "message", None) and hasattr(query, "edit_message_text"))
    if can_edit:
        if parts[1] == "retry" and row and row.status == "pending":
            text, markup = card(row, note=result, in_list=True)
            version = review_drafts.version(row, review_drafts.get(row.id))
            review_store.mark_notified(
                row.id, update.effective_user.id, row.fingerprint, row.status, version
            )
            try:
                await query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
                logger.warning("Could not edit retry card: %s", exc)
            except TelegramError:
                pass
        elif parts[1] in {"approve", "reject"}:
            done_icon = "✅" if parts[1] == "approve" else "⛔"
            done_title = "تأیید شد" if parts[1] == "approve" else "رد شد"
            done_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 بازگشت به صف بازبینی", callback_data="review:list:0")],
                [InlineKeyboardButton("🏠 داشبورد", callback_data="nav:home")],
            ])
            done_text = (
                f"{done_icon} <b>پیام #{parts[2]} {done_title}</b>\n\n"
                f"<blockquote>{escape(result)}</blockquote>"
            )
            try:
                await query.edit_message_text(
                    text=done_text,
                    reply_markup=done_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                return
            except BadRequest as exc:
                if "not modified" in str(exc).lower():
                    return
            except TelegramError:
                pass

    # Fallback when message cannot be edited in-place:
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except TelegramError:
        pass
    await update.effective_message.reply_text(result)
    if row and row.status == "pending":
        version = await send_card(context.bot, update.effective_user.id, row)
        review_store.mark_notified(
            row.id, update.effective_user.id, row.fingerprint, row.status, version
        )
