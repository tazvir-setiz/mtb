import logging
from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.auth import is_authorized, reject
from app.handlers.states import State, get_state, reset, set_state
from app.services.ai_settings import load_ai_settings, save_ai_value
from app.ui import keyboards

logger = logging.getLogger(__name__)


async def allowed(update: Update) -> bool:
    if not is_authorized(update):
        await reject(update)
        return False
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text(
            "تنظیمات فیلتر موضوعی را در گفت‌وگوی خصوصی با ربات تغییر دهید."
        )
        return False
    return True


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    reset(context.user_data)
    config = load_ai_settings()

    status_str = "🟢 روشن (فعال)" if config.topic_filter_enabled else "🔴 خاموش (غیرفعال)"
    action_str = "🗑 حذف مستقیم (DROP)" if config.off_topic_action == "DROP" else "📋 ارسال به بررسی مدیر (REVIEW)"

    if config.target_topics:
        topics_str = "\n".join(f"  • <code>{escape(topic)}</code>" for topic in config.target_topics)
    else:
        topics_str = "<i>هیچ موضوعی ثبت نشده است (در این حالت فیلتر پیامی را مسدود نمی‌کند).</i>"

    text = (
        "🎯 <b>فیلترینگ موضوعی پیام‌ها (هوش مصنوعی)</b>\n\n"
        f"وضعیت فیلتر: <b>{status_str}</b>\n"
        f"نحوه برخورد با پیام‌های غیرمرتبط: <b>{action_str}</b>\n\n"
        f"📌 <b>موضوعات مجاز برای فوروارد:</b>\n{topics_str}\n\n"
        "<i>با فعال بودن این قابلیت، هوش مصنوعی هر پیام را ارزیابی کرده و تنها پیام‌های مرتبط با موضوعات فوق فوروارد خواهند شد.</i>"
    )

    markup = keyboards.topics_menu(
        enabled=config.topic_filter_enabled,
        action=config.off_topic_action,
        topics=config.target_topics,
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup, do_quote=False)


async def toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    config = load_ai_settings()
    save_ai_value("topic_filter_enabled", "false" if config.topic_filter_enabled else "true")
    await show(update, context)


async def toggle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    config = load_ai_settings()
    new_action = "REVIEW" if config.off_topic_action == "DROP" else "DROP"
    save_ai_value("off_topic_action", new_action)
    await show(update, context)


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    reset(context.user_data)
    set_state(context.user_data, State.TOPIC_INPUT)
    config = load_ai_settings()

    current_topics = ", ".join(config.target_topics) if config.target_topics else "تعریف نشده"

    prompt_text = (
        "✏️ <b>ویرایش موضوعات مجاز</b>\n\n"
        f"موضوعات فعلی: <code>{escape(current_topics)}</code>\n\n"
        "لطفاً موضوعات دلخواه خود را ارسال کنید. می‌توانید چند موضوع را با کاما (، یا ,) از هم جدا نمایید.\n\n"
        "<b>مثال:</b>\n"
        "<code>اخبار هوش مصنوعی, فناوری و تکنولوژی, ارز دیجیتال</code>\n\n"
        "برای لغو می‌توانید /cancel را بزنید یا از دکمه‌های زیر استفاده کنید."
    )
    markup = keyboards.topic_edit_menu()
    await update.effective_message.reply_text(prompt_text, reply_markup=markup, do_quote=False)


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    save_ai_value("target_topics", "")
    await show(update, context)


async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await allowed(update):
        return
    text = (update.effective_message.text or "").strip()
    if not text:
        await update.effective_message.reply_text("متن واردشده خالی است.")
        return

    # Normalize Persian commas to English commas
    normalized_topics = text.replace("،", ",")
    save_ai_value("target_topics", normalized_topics)
    reset(context.user_data)

    await update.effective_message.reply_text("✅ موضوعات مجاز با موفقیت ذخیره شدند.")
    await show(update, context)
