from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_PRIMARY, STYLE_SUCCESS, _cb


def channel_confirm(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb("✅ تأیید", f"{prefix}:confirm", style=STYLE_SUCCESS),
                _cb("✏️ تغییر", f"{prefix}:change", style=STYLE_PRIMARY),
            ],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )


def destination_retry() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🔄 بررسی دوباره", "destination:retry", style=STYLE_PRIMARY)],
            [_cb("📖 راهنمای دسترسی", "destination:help")],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )
