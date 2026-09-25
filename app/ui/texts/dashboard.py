from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import _state_badge


def dashboard(
    source_title: str | None,
    destination_title: str | None,
    total_forwarded: int,
    auto_forward_enabled: bool = False,
) -> str:
    source_line = f"✅ <b>{_e(source_title)}</b>" if source_title else "⚠️ <i>تنظیم نشده</i>"
    dest_line = f"✅ <b>{_e(destination_title)}</b>" if destination_title else "⚠️ <i>تنظیم نشده</i>"
    ready = bool(source_title and destination_title)
    auto_line = "🟢 فعال" if auto_forward_enabled else "⚪ غیرفعال"

    return (
        "⚡ <b>Forwarder Control Center</b>\n"
        "<i>داشبورد مدیریت انتقال پیام</i>\n\n"
        f"<blockquote>"
        f"📥 مبدأ  ·  {source_line}\n"
        f"📤 مقصد  ·  {dest_line}\n"
        f"⚡ Auto-Forward  ·  <b>{auto_line}</b>\n"
        f"🧩 سیستم  ·  <b>{_state_badge(ready, 'آماده انتقال')}</b>"
        f"</blockquote>\n\n"
        f"📈 <b>{total_forwarded:,}</b> پیام با موفقیت منتقل شده\n\n"
        "<i>برای مدیریت هر بخش از دکمه‌های زیر استفاده کنید.</i>"
    )
