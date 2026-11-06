from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_DANGER, STYLE_PRIMARY, _cb


def stats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb("🔄 به‌روزرسانی آمار", "stats:refresh", style=STYLE_PRIMARY),
                _cb("🩺 تست سلامت", "system:health"),
            ],
            [
                _cb("🕘 پیام‌های اخیر", "menu:recent"),
                _cb("🔎 صف بازبینی", "menu:reviews"),
            ],
            [
                _cb("🗑 پاک کردن آمار", "stats:clear", style=STYLE_DANGER),
                _cb("‹ بازگشت به داشبورد", "nav:home"),
            ],
        ]
    )


def confirm_clear_statistics() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🗑 بله، آمار پاک شود", "stats:clear_confirm", style=STYLE_DANGER)],
            [_cb("لغو", "menu:stats", style=STYLE_PRIMARY)],
        ]
    )


def health_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🔄 بررسی مجدد سلامت", "system:health", style=STYLE_PRIMARY)],
            [_cb("‹ بازگشت به داشبورد", "nav:home")],
        ]
    )
