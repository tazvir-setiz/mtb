from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_PRIMARY, STYLE_SUCCESS, _cb


def channel_management(kind, channels, *, removing=False, page=0, pages=1):
    if removing:
        rows = [
            [_cb(f"🗑 {channel.title[:45]}", f"{kind}:remove:{channel.telegram_id}")]
            for channel in channels
        ]
    else:
        rows = [[_cb("➕ افزودن کانال", f"{kind}:add")], [_cb("🗑 حذف کانال", f"{kind}:removals")]]
    prefix = f"{kind}:removals" if removing else f"menu:{kind}"
    navigation = []
    if page:
        navigation.append(_cb("‹ صفحه قبل", f"{prefix}:{page - 1}"))
    if page + 1 < pages:
        navigation.append(_cb("صفحه بعد ›", f"{prefix}:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([_cb("‹ بازگشت", f"menu:{kind}" if removing else "nav:back")])
    return InlineKeyboardMarkup(rows)


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
