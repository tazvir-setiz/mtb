from __future__ import annotations

from telegram import InlineKeyboardMarkup

from app.ui.buttons.common import STYLE_DANGER, STYLE_PRIMARY, _cb


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb("📥 مبدأ", "menu:source"),
                _cb("📤 مقصد", "menu:destination"),
            ],
            [_cb("✍️ امضا / زیرنویس", "settings:signature", style=STYLE_PRIMARY)],
            [_cb("👤 آیدی‌های داخل پیام", "settings:usernames", style=STYLE_PRIMARY)],
            [_cb("🤖 تنظیمات هوش مصنوعی", "settings:ai", style=STYLE_PRIMARY)],
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


def username_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_cb("✏️ تعیین آیدی جایگزین", "usernames:replace", style=STYLE_PRIMARY)],
            [_cb("🗑 حذف آیدی‌ها از پیام", "usernames:delete", style=STYLE_DANGER)],
            [_cb("‹ تنظیمات", "menu:settings")],
        ]
    )


def ai_menu(enabled: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _cb(
                    "⏹ خاموش کردن AI" if enabled else "▶️ روشن کردن AI",
                    "ai:toggle",
                    style=STYLE_PRIMARY,
                )
            ],
            [
                _cb("🔑 ثبت کلید API", "ai:key"),
                _cb("🗑 حذف کلید", "ai:clear_key", style=STYLE_DANGER),
            ],
            [_cb("🌐 آدرس سرویس", "ai:url"), _cb("🧠 مدل", "ai:model")],
            [_cb("‹ تنظیمات", "menu:settings")],
        ]
    )
