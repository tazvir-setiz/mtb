from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import _state_badge


def dashboard(
    source_title: str | None,
    destination_title: str | None,
    total_forwarded: int,
    auto_forward_enabled: bool = False,
    ai_enabled: bool = False,
    signature_enabled: bool = False,
) -> str:
    source_line = f"✅ <b>{_e(source_title)}</b>" if source_title else "⚠️ <i>تنظیم نشده</i>"
    dest_line = f"✅ <b>{_e(destination_title)}</b>" if destination_title else "⚠️ <i>تنظیم نشده</i>"
    ready = bool(source_title and destination_title)
    auto_line = "🟢 فعال" if auto_forward_enabled else "⚪ غیرفعال"
    next_step = (
        "۱ از ۲ · کانال مبدأ را انتخاب کنید."
        if not source_title
        else "۲ از ۲ · کانال مقصد را انتخاب کنید."
        if not destination_title
        else "برای پیام‌های قبلی «انتقال پیام‌ها» و برای پیام‌های آینده «انتقال خودکار» را انتخاب کنید."
    )

    return (
        "🏠 <b>مرکز مدیریت انتقال</b>\n\n"
        f"<blockquote>"
        f"📥 مبدأ  ·  {source_line}\n"
        f"📤 مقصد  ·  {dest_line}\n"
        f"⚡ انتقال خودکار  ·  <b>{auto_line}</b>\n"
        f"🤖 پردازش هوشمند  ·  <b>{'روشن' if ai_enabled else 'خاموش'}</b>\n"
        f"✍️ امضا  ·  <b>{'فعال' if signature_enabled else 'بدون امضا'}</b>\n"
        f"🧩 تنظیم کانال‌ها  ·  <b>{_state_badge(ready, 'کامل')}</b>"
        f"</blockquote>\n\n"
        f"📈 <b>{total_forwarded:,}</b> پیام با موفقیت منتقل شده\n\n"
        f"<b>قدم بعدی</b>\n{next_step}"
    )
