from __future__ import annotations

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

STYLE_PRIMARY = "primary"


STYLE_SUCCESS = "success"


STYLE_DANGER = "danger"


def _cb(
    text: str,
    callback_data: str,
    *,
    style: str | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        style=style,
    )


def _copy(text: str, value: str | int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        copy_text=CopyTextButton(text=str(value)),
        style=STYLE_PRIMARY,
    )


def back_home(extra: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append(
        [
            _cb("‹ بازگشت", "nav:back"),
            _cb("🏠 داشبورد", "nav:home", style=STYLE_PRIMARY),
        ]
    )
    return InlineKeyboardMarkup(rows)


def cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_cb("✕ لغو و بازگشت", "nav:cancel", style=STYLE_DANGER)]])
