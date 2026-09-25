from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.handlers.dashboard import show_dashboard
from app.ui.messages import UNAUTHORIZED

logger = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or not settings.is_admin(user.id):
        await update.effective_message.reply_text(UNAUTHORIZED)
        logger.warning("Unauthorized access attempt by user_id=%s", user.id if user else "unknown")
        return
    await show_dashboard(update, context)
