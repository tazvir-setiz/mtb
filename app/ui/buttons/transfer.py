from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_DANGER, STYLE_PRIMARY, STYLE_SUCCESS, _cb


def transfer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🔢 انتقال یک بازه", "transfer:range", style=STYLE_SUCCESS)],
            [_cb("🎯 انتخاب شناسهٔ پیام‌ها", "transfer:ids", style=STYLE_PRIMARY)],
            [_cb("⚡ انتقال خودکار پیام‌های جدید", "transfer:new")],
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


def result_menu(has_errors: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        (
            [
                [
                    _cb("⚠️ خطاها", "transfer:errors", style=STYLE_DANGER),
                    _cb("↻ تلاش مجدد", "transfer:retry", style=STYLE_PRIMARY),
                ],
            ]
            if has_errors
            else []
        )
        + [
            [_cb("🚀 انتقال جدید", "menu:transfer", style=STYLE_SUCCESS)],
            [_cb("🏠 داشبورد", "nav:home")],
        ]
    )


def failed_messages_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("↻ تلاش مجدد برای همه", "transfer:retry", style=STYLE_PRIMARY)],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )


def _page_buttons(prefix, page, count):
    row = []
    if page:
        row.append(_cb("‹ صفحه قبل", f"{prefix}:{page - 1}"))
    if (page + 1) * 10 < count:
        row.append(_cb("صفحه بعد ›", f"{prefix}:{page + 1}"))
    return [row] if row else []


def source_selection(channels, page=0):
    return InlineKeyboardMarkup(
        [
            [_cb(c.title[:60], f"transfer:source:{c.telegram_id}")]
            for c in channels[page * 10 : (page + 1) * 10]
        ]
        + _page_buttons("transfer:sources", page, len(channels))
        + [[_cb("‹ بازگشت", "nav:back")]]
    )


def destination_selection(channels, chosen, page=0):
    rows = [
        [
            _cb(
                ("✅ " if c.telegram_id in chosen else "▫️ ") + c.title[:55],
                f"transfer:destination:{c.telegram_id}",
            )
        ]
        for c in channels[page * 10 : (page + 1) * 10]
    ]
    rows.extend(_page_buttons("transfer:destinations", page, len(channels)))
    rows.extend(
        [
            [_cb("ادامه با مقصدهای انتخاب‌شده", "transfer:routes")],
            [_cb("‹ انتخاب مبدأ", "menu:transfer")],
        ]
    )
    return InlineKeyboardMarkup(rows)
