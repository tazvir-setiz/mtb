import copy
import io
import logging
import secrets
from html import escape

from app.handlers.ai_settings import allowed
from app.handlers.states import State, get_state, reset, set_state
from app.services.guard_profile import (
    MAX_FILE_BYTES,
    MODES,
    TOPICS,
    decode_profile,
    encode_profile,
    load_profile,
    revision,
    save_profile,
)
from app.ui.buttons.guard import guard_confirm, guard_menu

logger = logging.getLogger(__name__)


async def show(update, context):
    if not await allowed(update):
        return
    reset(context.user_data)
    profile = load_profile()
    text = (
        "🛡 <b>تنظیمات گارد</b>\n\n"
        "با هر دکمه، حساسیت بعدی برای تأیید پیشنهاد می‌شود. برای تغییر قوانین و همه محدودیت‌های فنی، "
        "فایل JSON فعلی را دریافت، ویرایش و بارگذاری کنید.\n"
        "تغییرات پس از تأیید از پردازش بعدی اعمال می‌شوند؛ AI باید روشن باشد.\n"
        "حفاظت از دستورهای مدل و پاک‌سازی نهایی مستقل باقی می‌مانند."
    )
    markup = guard_menu(profile)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


async def export(update, context):
    if not await allowed(update):
        return
    reset(context.user_data)
    await update.effective_message.reply_document(
        document=io.BytesIO(encode_profile(load_profile())),
        filename="guard-settings.json",
        caption="تنظیمات فعلی گارد؛ بدون کلید API. پس از ویرایش، از «بارگذاری فایل» ارسال کنید.",
    )


async def ask(update, context):
    if not await allowed(update):
        return
    reset(context.user_data)
    set_state(context.user_data, State.GUARD_IMPORT)
    await update.effective_message.reply_text(
        "فایل تنظیمات را با پسوند .json و UTF-8 بفرستید (حداکثر ۶۴ کیلوبایت). "
        "فایل کامل جایگزین تنظیمات گارد می‌شود؛ قبل از ذخیره تغییرات نمایش داده می‌شوند. لغو: /cancel"
    )


async def preview(update, context, candidate, current):
    changes = []
    for group in ("sensitivity", "limits"):
        for key, value in candidate[group].items():
            previous = current[group][key]
            if value != previous:
                changes.append(f"{group}.{key}: {previous} → {value}")
    if candidate["instructions"] != current["instructions"]:
        changes.append("instructions: متن قوانین اختصاصی تغییر کرده است (متن کامل در فایل پیوست).")
    reset(context.user_data)
    if not changes:
        await update.effective_message.reply_text("تنظیمات فایل با تنظیمات فعلی یکسان است.")
        return
    token = secrets.token_hex(6)
    context.user_data["guard_pending"] = (token, candidate, revision(current))
    set_state(context.user_data, State.GUARD_CONFIRM)
    await update.effective_message.reply_document(
        document=io.BytesIO(encode_profile(candidate)),
        filename="guard-proposed.json",
        caption="نسخه کامل پیشنهادی برای بررسی؛ هنوز ذخیره نشده است.",
    )
    await update.effective_message.reply_text(
        "<b>تغییرات پیشنهادی گارد</b>\n<pre>" + escape("\n".join(changes)) + "</pre>\n"
        "پیام در حال پردازش با تنظیم قبلی تمام می‌شود. صف بررسی و پیام‌های قبلی خودکار بازپردازش نمی‌شوند.",
        reply_markup=guard_confirm(token),
    )


async def cycle(update, context):
    if not await allowed(update):
        return
    topic = update.callback_query.data.split(":")[-1]
    if topic not in TOPICS:
        return
    current = load_profile()
    candidate = copy.deepcopy(current)
    modes = list(MODES)
    candidate["sensitivity"][topic] = modes[
        (modes.index(current["sensitivity"][topic]) + 1) % len(modes)
    ]
    await preview(update, context, candidate, current)


async def receive(update, context):
    if not await allowed(update):
        return
    if get_state(context.user_data) != State.GUARD_IMPORT:
        await update.effective_message.reply_text(
            "برای ورود فایل، ابتدا تنظیمات ← گارد ← بارگذاری فایل را بزنید."
        )
        return
    document = update.message.document
    if (
        not document
        or not (document.file_name or "").lower().endswith(".json")
        or document.file_size is None
        or not 0 < document.file_size <= MAX_FILE_BYTES
    ):
        await update.effective_message.reply_text(
            "یک فایل .json با حجم حداکثر ۶۴ کیلوبایت بفرستید."
        )
        return
    try:
        file = await document.get_file()
        raw = await file.download_as_bytearray()
        candidate = decode_profile(raw)
    except ValueError as exc:
        await update.effective_message.reply_text(escape(str(exc)))
        return
    except Exception as exc:
        logger.warning("Guard profile download failed type=%s", type(exc).__name__)
        await update.effective_message.reply_text("دریافت فایل ناموفق بود؛ دوباره تلاش کنید.")
        return
    await preview(update, context, candidate, load_profile())


async def apply(update, context):
    if not await allowed(update):
        return
    pending = context.user_data.get("guard_pending")
    token = update.callback_query.data.split(":")[-1]
    if get_state(context.user_data) != State.GUARD_CONFIRM or not pending or pending[0] != token:
        await update.effective_message.reply_text(
            "این تأیید منقضی شده؛ تنظیمات را دوباره باز کنید."
        )
        return
    try:
        save_profile(pending[1], pending[2])
    except ValueError as exc:
        reset(context.user_data)
        await update.effective_message.reply_text(escape(str(exc)))
        return
    logger.info(
        "Guard profile updated admin=%s revision=%s",
        update.effective_user.id,
        revision(pending[1])[:12],
    )
    await show(update, context)
    await update.effective_message.reply_text(
        "✅ تنظیمات گارد ذخیره شد؛ از پردازش بعدی اعمال می‌شود."
    )
