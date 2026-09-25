from __future__ import annotations

from datetime import datetime

from app.database.models import MessageStatus

STATUS_ICONS = {
    MessageStatus.SUCCESS: "✅",
    MessageStatus.FAILED: "❌",
    MessageStatus.SKIPPED: "⏭",
    MessageStatus.DUPLICATE: "⏭",
}


def format_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def status_icon(status: MessageStatus) -> str:
    return STATUS_ICONS.get(status, "❔")
