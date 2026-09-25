from __future__ import annotations

import time

from telegram import Bot
from telegram.error import BadRequest

from app.telegram.forward_service import ProgressSnapshot
from app.ui import keyboards, messages


class ProgressReporter:
    """
    مسئول ویرایش پیام Progress در چت ادمین بدون ارسال پیام جدید برای هر مرحله.
    """

    def __init__(self, bot: Bot, chat_id: int, message_id: int, started_at: float | None = None):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.started_at = started_at or time.monotonic()

    async def update(self, snapshot: ProgressSnapshot) -> None:
        elapsed = int(time.monotonic() - self.started_at)
        if snapshot.stopped:
            text = messages.paused_text(
                snapshot.processed, snapshot.total, snapshot.success, snapshot.failed
            )
            markup = keyboards.paused_menu()
        else:
            text = messages.progress_text(
                snapshot.processed,
                snapshot.total,
                snapshot.success,
                snapshot.skipped,
                snapshot.failed,
                elapsed,
            )
            markup = keyboards.in_progress()
        try:
            await self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=self.message_id,
                text=text,
                reply_markup=markup,
            )
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
