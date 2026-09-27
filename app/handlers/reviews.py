import asyncio
import json
import logging
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TelegramError
from telethon.extensions import html

from app.config import settings
from app.handlers import review_edit
from app.handlers.auth import is_authorized, reject
from app.services import review_drafts, review_store
from app.services.review_service import decide
from app.telegram.client import ensure_started

logger = logging.getLogger(__name__)
REASONS = {
    "ai_draft": "پیش‌نویس بازنگری AI آمادهٔ تصمیم شماست؛ هنوز ارسال نشده",
    "manual_draft": "ویرایش شما ذخیره شد؛ برای ارسال تأیید کنید",
    "ai_rejected": "AI پیشنهاد رد داده؛ تصمیم نهایی با شماست",
    "rewrite_failed": "بازنویسی نتوانست از بررسی نهایی قوانین عبور کند",
    "timeout": "مهلت پاسخ AI تمام شد؛ می‌توانید بررسی با AI را دوباره اجرا کنید",
    "response_truncated": "پاسخ مدل به سقف توکن رسید و ناقص ماند",
    "provider_refusal": "سرویس پاسخ قابل انتشار تولید نکرد",
    "invalid_output": "قالب پاسخ مدل معتبر نبود",
    "missing_api_key": "کلید API تنظیم نشده است",
    "invalid_credentials": "سرویس کلید API یا دسترسی حساب را نپذیرفت",
    "rate_limit": "محدودیت درخواست یا اعتبار سرویس AI",
    "bad_request": "آدرس، مدل یا پارامترهای درخواست AI پذیرفته نشد",
    "provider_error": "خطای HTTP سرویس AI",
    "connection_error": "اتصال به سرویس AI برقرار نشد",
    "poll": "نظرسنجی نیاز به تأیید مدیر دارد",
    "low_confidence": "اطمینان مدل کافی نیست",
    "review": "مدل درباره محتوای پیام مطمئن نیست",
    "political": "پس از بازنگری خودکار، مدل همچنان پیام را موضع‌گیری یا تبلیغ سیاسی تشخیص داده است",
    "service_unavailable": "سرویس AI خطا داده یا پاسخ معتبر نداده است",
    "circuit_open": "سرویس AI موقتاً در دوره توقف پس از خطاست",
    "input_too_long": "طول پیام بیش از سقف بررسی خودکار است",
    "unsafe_output": "خروجی از بررسی نهایی پاک‌سازی عبور نکرد",
    "content_changed": "محتوای پیام پس از درخواست قبلی تغییر کرده است",
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


def card(row):
    reason = REASONS.get(row.reason, "محتوا نیاز به تصمیم مدیر دارد")
    text = (
        f"🔎 بررسی پیام #{row.id}\nمبدأ: {row.source_id} — پیام: {row.message_id}\n"
        f"مقصد ثابت این درخواست: {row.destination_id}\nدلیل: {reason}\n\n"
        f"پیش‌نمایش کوتاه:\n{escaped_preview(row.preview)}\n\n"
        "«بررسی دوباره با AI» پیش‌نویس می‌سازد و خودکار ارسال نمی‌کند. تأیید، نسخهٔ فعلی را می‌فرستد؛ لینک‌ها و آیدی‌ها پاک‌سازی "
        "و امضای فعلی اضافه می‌شود. نظرسنجی با تأیید شما مستقیم فوروارد می‌شود."
    )
    buttons = []
    if row.status == "pending":
        suffix = f"{row.id}:{review_drafts.version(row)}"
        buttons.append(
            [InlineKeyboardButton("🤖 بررسی دوباره با AI", callback_data=f"review:retry:{suffix}")]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    "✅ تأیید نسخهٔ فعلی", callback_data=f"review:approve:{suffix}"
                ),
                InlineKeyboardButton("✏️ ویرایش", callback_data=f"review:edit:{suffix}"),
                InlineKeyboardButton("⛔ رد پیام", callback_data=f"review:reject:{suffix}"),
            ]
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
    await bot.send_message(
        chat_id=admin_id,
        text=text,
        reply_markup=markup,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    return version


async def notify_pending(bot):
    after_id = 0
    while True:
        try:
            rows = review_store.pending(after_id=after_id)
            for row in rows:
                after_id = row.id
                if row.status == "sending":
                    continue
                for admin_id in settings.admin_ids:
                    if admin_id in json.loads(row.notified):
                        continue
                    try:
                        version = await send_card(bot, admin_id, row)
                        review_store.mark_notified(
                            row.id, admin_id, row.fingerprint, row.status, version
                        )
                    except RetryAfter as exc:
                        delay = exc.retry_after
                        await asyncio.sleep(
                            delay.total_seconds() if hasattr(delay, "total_seconds") else delay
                        )
                    except Exception as exc:
                        logger.warning(
                            "Review notification failed review_id=%d admin=%s type=%s; available via /reviews",
                            row.id,
                            admin_id,
                            type(exc).__name__,
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
    if not rows:
        await update.effective_message.reply_text("پیام دیگری برای بررسی وجود ندارد.")
        return
    for row in rows:
        await send_card(context.bot, update.effective_user.id, row)
        await asyncio.sleep(1.1)
    await update.effective_message.reply_text(
        "ادامه فهرست بررسی:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("موارد بعدی", callback_data=f"review:list:{rows[-1].id}")]]
        ),
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
        await send_card(context.bot, update.effective_user.id, row)
