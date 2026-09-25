from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_DANGER, STYLE_PRIMARY, STYLE_SUCCESS, _cb


def transfer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🔢 انتقال یک بازه", "transfer:range", style=STYLE_SUCCESS)],
            [_cb("🎯 انتخاب Message IDها", "transfer:ids", style=STYLE_PRIMARY)],
            [_cb("⚡ پیام‌های جدید", "transfer:new")],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )


def range_summary() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("ادامه و بررسی نهایی ›", "transfer:start", style=STYLE_PRIMARY)],
            [
                _cb("✏️ ویرایش", "transfer:edit"),
                _cb("✕ لغو", "nav:cancel", style=STYLE_DANGER),
            ],
        ]
    )


def confirm_transfer() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🚀 شروع انتقال", "transfer:confirm", style=STYLE_SUCCESS)],
            [_cb("✕ لغو عملیات", "nav:cancel", style=STYLE_DANGER)],
        ]
    )


def in_progress() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_cb("⏸ توقف عملیات", "transfer:pause", style=STYLE_PRIMARY)]])


def paused_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("▶️ ادامه انتقال", "transfer:resume", style=STYLE_SUCCESS)],
            [_cb("↻ شروع مجدد", "transfer:restart", style=STYLE_PRIMARY)],
            [_cb("🏠 داشبورد", "nav:home")],
        ]
    )


def result_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb("⚠️ خطاها", "transfer:errors", style=STYLE_DANGER),
                _cb("↻ Retry", "transfer:retry", style=STYLE_PRIMARY),
            ],
            [_cb("🚀 انتقال جدید", "menu:transfer", style=STYLE_SUCCESS)],
            [_cb("🏠 داشبورد", "nav:home")],
        ]
    )


def failed_messages_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("↻ Retry همه", "transfer:retry", style=STYLE_PRIMARY)],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )
