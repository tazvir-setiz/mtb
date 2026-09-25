from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER

HELP_TEXT = (
    "❓ <b>راهنمای Forwarder</b>\n"
    f"{DIVIDER}\n\n"
    "برای شروع فقط سه مرحله لازم است:\n\n"
    "1️⃣ کانال <b>مبدأ</b> را تنظیم کنید.\n"
    "2️⃣ کانال <b>مقصد</b> را تنظیم و دسترسی ارسال را بررسی کنید.\n"
    "3️⃣ انتقال دستی را اجرا کنید یا <b>Auto-Forward</b> را روشن کنید.\n\n"
    "<blockquote expandable>"
    "<b>روش‌های انتقال</b>\n"
    "• بازه Message ID برای پیام‌های پشت‌سرهم\n"
    "• لیست Message ID برای پیام‌های انتخابی\n\n"
    "<b>Auto-Forward</b>\n"
    "پیام‌های جدید مبدأ را به‌صورت خودکار پردازش و ارسال می‌کند.\n\n"
    "<b>نکته</b>\n"
    "کانال مقصد باید مجوز ارسال پیام داشته باشد و تنظیمات AI/امضا در زمان ارسال اعمال می‌شوند."
    "</blockquote>"
)


def settings_text(
    signature: str | None,
    forward_delay: float | None = None,
    ai_enabled: bool | None = None,
) -> str:
    if signature:
        preview = signature.strip()
        if len(preview) > 180:
            preview = preview[:177] + "..."
        signature_line = f"✅ تنظیم شده\n<code>{_e(preview)}</code>"
    else:
        signature_line = "⚪ تنظیم نشده"

    delay_line = f"{forward_delay:g} ثانیه" if forward_delay is not None else "—"
    ai_line = "🟢 فعال" if ai_enabled is True else "⚪ غیرفعال" if ai_enabled is False else "—"

    return (
        "⚙️ <b>تنظیمات</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"⏱ فاصله ارسال  <b>{delay_line}</b>\n"
        f"🧠 AI Guardrails  <b>{ai_line}</b>\n"
        f"✍️ امضا  {signature_line}"
        "</blockquote>\n\n"
        "<i>تنظیمات حساس با تأیید دوباره اعمال می‌شوند.</i>"
    )


def ask_signature() -> str:
    return (
        "✍️ <b>امضا / زیرنویس</b>\n\n"
        "متنی را که باید زیر پیام‌های منتقل‌شده قرار بگیرد ارسال کنید.\n"
        "فرمت‌های Telegram مثل <b>Bold</b>، <i>Italic</i> و لینک حفظ می‌شوند.\n\n"
        "<blockquote>"
        "برای رسانه‌ها، محدودیت طول Caption تلگرام را در نظر بگیرید."
        "</blockquote>"
    )


def clear_data_confirm_text() -> str:
    return (
        "🗑 <b>پاک کردن داده‌های عملیات؟</b>\n\n"
        "تاریخچه Jobها و پیام‌های ثبت‌شده حذف می‌شود، اما تنظیم کانال‌ها و امضا باقی می‌ماند.\n\n"
        "<b>این عملیات قابل بازگشت نیست.</b>"
    )
