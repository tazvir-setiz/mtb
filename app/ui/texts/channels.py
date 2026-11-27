from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER


def channel_list(kind, channels, offset=0):
    title = "📥 کانال‌های مبدأ" if kind == "source" else "📤 کانال‌های مقصد"
    lines = [f"<b>{title}</b>", ""]
    lines.extend(
        f"{i}. {_e(c.title[:80])} · <code>{c.telegram_id}</code>"
        for i, c in enumerate(channels, offset + 1)
    )
    return "\n".join(lines) if channels else "\n".join(lines) + "هنوز کانالی تنظیم نشده است."


def seen_channels_block(seen) -> str:
    """List chats the bot has received updates from, with their numeric ids.

    Bale cannot always resolve a channel from a link/username, so these ids are the
    reliable way for the admin to add one.
    """
    if not seen:
        return ""
    rows = "\n".join(
        f"• {_e((item.get('title') or 'بدون نام')[:60])} — <code>{item.get('id')}</code>"
        for item in seen[:5]
    )
    return f"\n\n<b>کانال‌هایی که ربات دیده است</b>\n<blockquote>{rows}</blockquote>"


def ask_channel(kind: str, current_title: str | None, seen=None) -> str:
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
        f"کانال‌های تنظیم‌شده: {current}\n"
        f"{seen_channels_block(seen)}\n\n"
        "افزودن کانال جدید، کانال‌های قبلی را حفظ می‌کند.\n\n"
        "<b>راه‌های ساده برای انتخاب کانال:</b>\n"
        "• اگر کانال در دکمه‌های زیر هست، روی آن بزنید.\n"
        "• یک پیام از کانال مورد نظر به اینجا <b>فوروارد</b> کنید.\n"
        "• در تلگرام می‌توانید از دکمهٔ «📢 انتخاب کانال از تلگرام» استفاده کنید.\n\n"
        "یا شناسه، Username یا لینک کانال را بفرستید:\n"
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
