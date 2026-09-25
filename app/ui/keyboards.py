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


def main_menu(
    source_ready: bool,
    destination_ready: bool,
    auto_forward_enabled: bool = False,
    source_id: int | None = None,
    destination_id: int | None = None,
) -> InlineKeyboardMarkup:
    ready = source_ready and destination_ready

    rows: list[list[InlineKeyboardButton]] = [
        [
            _cb(
                "📥 مبدأ" if not source_ready else "✅ مبدأ",
                "menu:source",
                style=STYLE_SUCCESS if source_ready else STYLE_PRIMARY,
            ),
            _cb(
                "📤 مقصد" if not destination_ready else "✅ مقصد",
                "menu:destination",
                style=STYLE_SUCCESS if destination_ready else STYLE_PRIMARY,
            ),
        ]
    ]

    copy_row: list[InlineKeyboardButton] = []
    if source_id is not None:
        copy_row.append(_copy("📋 ID مبدأ", source_id))
    if destination_id is not None:
        copy_row.append(_copy("📋 ID مقصد", destination_id))
    if copy_row:
        rows.append(copy_row)

    if ready:
        rows.append([_cb("🚀 انتقال پیام‌ها", "menu:transfer", style=STYLE_SUCCESS)])
        rows.append(
            [
                _cb(
                    "🟢 Auto-Forward روشن" if auto_forward_enabled else "⚪ Auto-Forward خاموش",
                    "menu:auto_toggle",
                    style=STYLE_SUCCESS if auto_forward_enabled else STYLE_PRIMARY,
                )
            ]
        )

    rows.extend(
        [
            [
                _cb("🕘 اخیر", "menu:recent"),
                _cb("📊 آمار", "menu:stats", style=STYLE_PRIMARY),
            ],
            [
                _cb("⚙️ تنظیمات", "menu:settings"),
                _cb("❓ راهنما", "menu:help"),
            ],
        ]
    )

    return InlineKeyboardMarkup(rows)


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
    return InlineKeyboardMarkup(
        [[_cb("✕ لغو و بازگشت", "nav:cancel", style=STYLE_DANGER)]]
    )


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
    return InlineKeyboardMarkup(
        [[_cb("⏸ توقف عملیات", "transfer:pause", style=STYLE_PRIMARY)]]
    )


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


def stats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🔄 به‌روزرسانی", "stats:refresh", style=STYLE_PRIMARY)],
            [_cb("🗑 پاک کردن آمار", "stats:clear", style=STYLE_DANGER)],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )


def confirm_clear_statistics() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🗑 بله، آمار پاک شود", "stats:clear_confirm", style=STYLE_DANGER)],
            [_cb("لغو", "menu:stats", style=STYLE_PRIMARY)],
        ]
    )


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb("📥 مبدأ", "menu:source"),
                _cb("📤 مقصد", "menu:destination"),
            ],
            [_cb("✍️ امضا / زیرنویس", "settings:signature", style=STYLE_PRIMARY)],
            [_cb("⏱ فاصله ارسال", "settings:delay")],
            [_cb("🗑 پاک کردن داده‌های عملیات", "settings:clear_data", style=STYLE_DANGER)],
            [_cb("‹ بازگشت", "nav:back")],
        ]
    )


def confirm_clear_data() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb(
                    "🗑 بله، داده‌های عملیات پاک شود",
                    "settings:clear_data_confirm",
                    style=STYLE_DANGER,
                )
            ],
            [_cb("لغو", "menu:settings", style=STYLE_PRIMARY)],
        ]
    )


def signature_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("🗑 حذف امضای فعلی", "settings:clear_sig", style=STYLE_DANGER)],
            [_cb("✕ لغو", "nav:cancel")],
        ]
    )
