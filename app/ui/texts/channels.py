from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER


def ask_channel(kind: str, current_title: str | None) -> str:
    label = "📥 <b>کانال مبدأ</b>" if kind == "source" else "📤 <b>کانال مقصد</b>"
    current = f"✅ <b>{_e(current_title)}</b>" if current_title else "⚠️ <i>تنظیم نشده</i>"
    permission_hint = (
        "ربات/کلاینت متصل باید به کانال دسترسی خواندن داشته باشد."
        if kind == "source"
        else "در مقصد، دسترسی ارسال پیام لازم است."
    )

    return (
        f"{label}\n"
        f"{DIVIDER}\n\n"
        f"کانال فعلی: {current}\n\n"
        "شناسه، Username یا لینک کانال را ارسال کنید.\n\n"
        "<blockquote>"
        "<code>@channel_username</code>\n"
        "<code>-1001234567890</code>\n"
        "<code>https://t.me/channel_username</code>"
        "</blockquote>\n"
        f"<i>{permission_hint}</i>"
    )


def channel_confirmed(kind: str, title: str, telegram_id: int, username: str | None) -> str:
    label = "مبدأ" if kind == "source" else "مقصد"
    username_line = f"@{_e(username)}" if username else "—"

    return (
        f"✅ <b>کانال {label} شناسایی شد</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📢 <b>{_e(title)}</b>\n"
        f"🆔 <code>{telegram_id}</code>\n"
        f"👤 {username_line}"
        "</blockquote>\n\n"
        "اطلاعات را بررسی و تأیید کنید."
    )


PERMISSION_ERROR = (
    "🛡 <b>دسترسی مقصد کامل نیست</b>\n\n"
    "ربات یا حساب متصل باید در کانال مقصد Administrator باشد و اجازه ارسال پیام داشته باشد."
)


CHANNEL_NOT_FOUND = (
    "⚠️ <b>کانال پیدا نشد</b>\n\n"
    "شناسه، Username یا لینک را بررسی کنید و مطمئن شوید حساب متصل به کانال دسترسی دارد."
)
