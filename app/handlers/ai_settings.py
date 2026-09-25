import logging
from html import escape

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.handlers.auth import is_authorized, reject
from app.handlers.states import State, get_state, reset, set_state
from app.services.ai_settings import load_ai_settings, save_ai_value, validate_ai_value
from app.ui import keyboards

logger = logging.getLogger(__name__)
INPUT_FIELDS = {
    State.AI_KEY_INPUT: "api_key",
    State.AI_URL_INPUT: "base_url",
    State.AI_MODEL_INPUT: "model",
}
PROMPTS = {
    "api_key": "کلید API سرویس را بفرستید. پیام کلید پس از دریافت حذف می‌شود؛ برای لغو /cancel.",
    "base_url": (
        "آدرس کامل سرویس را به‌صورت متن ساده بفرستید؛ مثال:\n"
        "<code>https://api.openai.com/v1/chat/completions</code>\n\n"
        "با تغییر آدرس، کلید قبلی پاک و AI خاموش می‌شود تا کلید به سرویس دیگری ارسال نشود."
    ),
    "model": "نام مدل را بفرستید؛ مثلاً <code>gpt-4o-mini</code>.",
}


async def allowed(update: Update) -> bool:
    if not is_authorized(update):
        await reject(update)
        return False
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "تنظیمات AI را در گفت‌وگوی خصوصی با ربات تغییر دهید."
        )
        return False
    return True


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    reset(context.user_data)
    config = load_ai_settings()
    text = (
        "🤖 <b>تنظیمات هوش مصنوعی</b>\n\n"
        f"وضعیت: <b>{'روشن' if config.enabled else 'خاموش'}</b>\n"
        f"کلید API: <b>{'ثبت شده' if config.api_key else 'ثبت نشده'}</b>\n"
        f"آدرس سرویس: <code>{escape(config.base_url)}</code>\n"
        f"مدل: <code>{escape(config.model)}</code>\n\n"
        "تغییرات ذخیره می‌شوند و از پیام بعدی اعمال می‌شوند."
    )
    markup = keyboards.ai_menu(config.enabled)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup, do_quote=False)


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str) -> None:
    if not await allowed(update):
        return
    reset(context.user_data)
    state = next(state for state, name in INPUT_FIELDS.items() if name == field)
    set_state(context.user_data, state)
    await update.effective_message.reply_text(
        PROMPTS[field], reply_markup=keyboards.cancel_only(force_reply=True)
    )


async def toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    config = load_ai_settings()
    if not config.enabled:
        for field in ("base_url", "api_key", "model"):
            if validate_ai_value(field, getattr(config, field)):
                await update.effective_message.reply_text(
                    "ابتدا آدرس سرویس، کلید معتبر و مدل را تنظیم کنید."
                )
                return
    save_ai_value("enabled", "false" if config.enabled else "true")
    await show(update, context)


async def clear_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    save_ai_value("api_key", "")
    await show(update, context)


async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    field = INPUT_FIELDS.get(get_state(context.user_data))
    if field is None:
        return
    value = update.message.text.strip()
    if field == "api_key":
        try:
            await update.message.delete()
        except TelegramError:
            await update.message.reply_text(
                "حذف پیام کلید ممکن نشد؛ لطفاً خودتان آن پیام را حذف کنید.", do_quote=False
            )
    error = validate_ai_value(field, value)
    if error:
        await update.message.reply_text(error, do_quote=False)
        return
    try:
        save_ai_value(field, value)
    except Exception as exc:
        logger.warning("AI setting could not be saved (%s)", type(exc).__name__)
        await update.message.reply_text("ذخیره انجام نشد؛ دوباره تلاش کنید.", do_quote=False)
        return
    await show(update, context)
