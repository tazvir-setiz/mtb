from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.handlers.states import State, reset, set_state
from app.services.text_sanitizer import USERNAME_SETTING, VALID_USERNAME, username_replacement
from app.ui import keyboards


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context.user_data)
    replacement = username_replacement()
    status = f"جایگزینی با <code>{replacement}</code>" if replacement else "حذف آیدی‌ها"
    text = (
        "👤 <b>آیدی‌های داخل پیام</b>\n\n"
        f"وضعیت فعلی: {status}\n\n"
        "آیدی‌های داخل متن و کپشن پیام‌ها حذف می‌شوند یا با آیدی دلخواه شما جایگزین می‌شوند. "
        "این تنظیم حتی با AI خاموش اعمال می‌شود. امضای تنظیم‌شدهٔ شما تغییر نمی‌کند."
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboards.username_menu())
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboards.username_menu())


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(context.user_data, State.USERNAME_INPUT)
    await update.callback_query.message.reply_text(
        "آیدی جایگزین را ارسال کنید؛ مثلاً <code>@MyChannel</code>\n"
        "۵ تا ۳۲ کاراکتر انگلیسی، عدد یا زیرخط؛ شروع با حرف انگلیسی.",
        reply_markup=keyboards.cancel_only(force_reply=True),
    )


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        SettingsRepository.set(session, USERNAME_SETTING, "")
    await show(update, context)


async def save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    value = update.message.text.strip()
    if not value.startswith("@"):
        value = "@" + value
    if not VALID_USERNAME.fullmatch(value):
        await update.message.reply_text("آیدی معتبر نیست. نمونه: @MyChannel — برای لغو /cancel")
        return
    with get_session() as session:
        SettingsRepository.set(session, USERNAME_SETTING, value)
    await show(update, context)
