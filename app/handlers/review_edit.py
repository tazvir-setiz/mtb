from html import escape

from telegram import ForceReply

from app.handlers.states import State, reset, set_state
from app.services import review_drafts, review_store
from app.services.text_sanitizer import sanitize_text


async def begin(update, context, row, version):
    if row.reason == "poll":
        await update.effective_message.reply_text(
            "ویرایش محتوای نظرسنجی پشتیبانی نمی‌شود؛ اصل آن را تأیید یا رد کنید."
        )
        return
    if row.status != "pending" or review_drafts.version(row) != version:
        await update.effective_message.reply_text("این نسخه دیگر قابل ویرایش نیست. /reviews")
        return
    prompt = await update.effective_message.reply_text(
        "متن کامل جایگزین را در پاسخ به همین پیام بفرستید (حداکثر ۴۰۰۰ نویسه). "
        "متن ذخیره و برای تأیید نمایش داده می‌شود؛ هنوز ارسال نمی‌شود. لغو: /cancel",
        reply_markup=ForceReply(selective=True),
    )
    reset(context.user_data)
    context.user_data["review_edit"] = (row.id, version, prompt.message_id)
    set_state(context.user_data, State.REVIEW_EDIT)


async def save(update, context):
    from app.handlers.reviews import send_card

    if update.effective_chat.type != "private":
        return
    draft = context.user_data.get("review_edit")
    if not draft:
        reset(context.user_data)
        return
    review_id, version, prompt_id = draft
    reply = update.message.reply_to_message
    if not reply or reply.message_id != prompt_id:
        await update.effective_message.reply_text(
            "برای ویرایش، به پیام درخواست متن پاسخ بدهید؛ یا /cancel بزنید."
        )
        return
    text = (update.message.text or "").strip()
    if not text or len(text) > 4000:
        await update.effective_message.reply_text("متن باید بین ۱ و ۴۰۰۰ نویسه باشد.")
        return
    text = sanitize_text(escape(text), remove_links=True)
    if not text.strip():
        await update.effective_message.reply_text("متن پس از پاک‌سازی خالی است.")
        return
    saved = review_drafts.save(review_id, version, text, "manual_draft")
    reset(context.user_data)
    if not saved:
        await update.effective_message.reply_text(
            "درخواست هم‌زمان تغییر کرده است؛ از /reviews دوباره ویرایش کنید."
        )
        return
    await send_card(context.bot, update.effective_user.id, review_store.get(review_id))
