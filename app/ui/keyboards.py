from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu(source_ready: bool, destination_ready: bool, auto_forward_enabled: bool = False) -> InlineKeyboardMarkup:
    transfer_row = (
        [InlineKeyboardButton("🚀 انتقال پیام‌ها", callback_data="menu:transfer")]
        if source_ready and destination_ready
        else []
    )
    auto_row = []
    if source_ready and destination_ready:
        label = "🟢 Auto-Forward: روشن" if auto_forward_enabled else "🔴 Auto-Forward: خاموش"
        auto_row = [InlineKeyboardButton(label, callback_data="menu:auto_toggle")]

    rows = [
        [
            InlineKeyboardButton("📥 کانال مبدأ", callback_data="menu:source"),
            InlineKeyboardButton("📤 کانال مقصد", callback_data="menu:destination"),
        ],
        transfer_row,
        auto_row,
        [
            InlineKeyboardButton("📋 پیام‌های اخیر", callback_data="menu:recent"),
            InlineKeyboardButton("📊 آمار", callback_data="menu:stats"),
        ],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="menu:settings")],
        [InlineKeyboardButton("❓ راهنما", callback_data="menu:help")],
    ]
    rows = [r for r in rows if r]
    return InlineKeyboardMarkup(rows)


def back_home(extra: list[list[InlineKeyboardButton]] | None = None) -> InlineKeyboardMarkup:
    rows = list(extra or [])
    rows.append(
        [
            InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back"),
            InlineKeyboardButton("🏠 خانه", callback_data="nav:home"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def cancel_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="nav:cancel")]])


def channel_confirm(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ تأیید", callback_data=f"{prefix}:confirm")],
            [InlineKeyboardButton("🔄 تغییر", callback_data=f"{prefix}:change")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )


def destination_retry() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 بررسی مجدد", callback_data="destination:retry")],
            [InlineKeyboardButton("📖 راهنما", callback_data="destination:help")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )


def transfer_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔢 انتقال بازه پیام‌ها", callback_data="transfer:range")],
            [InlineKeyboardButton("📋 انتخاب Message IDها", callback_data="transfer:ids")],
            [InlineKeyboardButton("🆕 پیام‌های جدید", callback_data="transfer:new")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )


def range_summary() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 شروع انتقال", callback_data="transfer:start")],
            [InlineKeyboardButton("✏️ ویرایش", callback_data="transfer:edit")],
            [InlineKeyboardButton("❌ لغو", callback_data="nav:cancel")],
        ]
    )


def confirm_transfer() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 بله، شروع کن", callback_data="transfer:confirm")],
            [InlineKeyboardButton("❌ لغو", callback_data="nav:cancel")],
        ]
    )


def in_progress() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏸ توقف", callback_data="transfer:pause")]])


def paused_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ ادامه", callback_data="transfer:resume")],
            [InlineKeyboardButton("🔄 شروع مجدد", callback_data="transfer:restart")],
            [InlineKeyboardButton("🏠 خانه", callback_data="nav:home")],
        ]
    )


def result_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 مشاهده خطاها", callback_data="transfer:errors")],
            [InlineKeyboardButton("🔄 Retry موارد ناموفق", callback_data="transfer:retry")],
            [InlineKeyboardButton("🚀 انتقال جدید", callback_data="menu:transfer")],
            [InlineKeyboardButton("🏠 خانه", callback_data="nav:home")],
        ]
    )


def failed_messages_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Retry همه", callback_data="transfer:retry")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )


def stats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 بروزرسانی", callback_data="stats:refresh")],
            [InlineKeyboardButton("🧹 پاک کردن آمار", callback_data="stats:clear")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 کانال مبدأ", callback_data="menu:source")],
            [InlineKeyboardButton("📤 کانال مقصد", callback_data="menu:destination")],
            [InlineKeyboardButton("⏱ فاصله Forward", callback_data="settings:delay")],
            [InlineKeyboardButton("✍️ تنظیم زیرنویس (امضا)", callback_data="settings:signature")],  # 👈 اضافه شد
            [InlineKeyboardButton("🧹 پاک کردن داده‌ها", callback_data="settings:clear_data")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="nav:back")],
        ]
    )

def signature_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🗑 حذف امضای فعلی", callback_data="settings:clear_sig")],
            [InlineKeyboardButton("❌ لغو", callback_data="nav:cancel")],
        ]
    )