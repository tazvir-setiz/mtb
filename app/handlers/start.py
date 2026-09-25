from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.auth import is_authorized, reject
from app.handlers.dashboard import show_dashboard

logger = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(update):
        await reject(update)
        logger.warning("Unauthorized access attempt by user_id=%s", user.id if user else "unknown")
        return
    await show_dashboard(update, context)
