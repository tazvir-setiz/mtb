from telegram import Update

from app.config import settings
from app.telegram.callback_ack import ack
from app.ui import messages


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    return user is not None and settings.is_admin(user.id)


async def reject(update: Update) -> None:
    if update.callback_query:
        await ack(update.callback_query, messages.UNAUTHORIZED, show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(messages.UNAUTHORIZED)
