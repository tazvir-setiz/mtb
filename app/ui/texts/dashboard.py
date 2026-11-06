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
    *,
    pending_reviews: int = 0,
    ai_model: str | None = None,
) -> str:
    source_line = f"✅ <b>{_e(source_title)}</b>" if source_title else "⚠️ <i>تنظیم نشده</i>"
    dest_line = f"✅ <b>{_e(destination_title)}</b>" if destination_title else "⚠️ <i>تنظیم نشده</i>"
    ready = bool(source_title and destination_title)
    auto_line = "🟢 روشن (شنود زنده)" if auto_forward_enabled else "⚪ خاموش"

    if ai_enabled and ai_model:
        ai_line = f"🟢 روشن (<code>{_e(ai_model[:24])}</code>)"
    elif ai_enabled:
        ai_line = "🟢 روشن"
    else:
        ai_line = "⚪ خاموش"

    next_step = (
        "۱ از ۲ · کانال مبدأ را انتخاب کنید."
        if not source_title
        else "۲ از ۲ · کانال مقصد را انتخاب کنید."
        if not destination_title
        else "برای پیام‌های قبلی «انتقال پیام‌ها» و برای پیام‌های آینده «انتقال خودکار» را انتخاب کنید."
    )

    review_badge = (
        f"\n⚠️ پیام‌های در انتظار تصمیم مدیر: <b>{pending_reviews}</b>"
        if pending_reviews > 0
        else ""
    )

    return (
        "🏠 <b>مرکز فرماندهی و انتقال پیام</b>\n\n"
        f"<blockquote>"
        f"📥 مبداها  ·  {source_line}\n"
        f"📤 مقصدها  ·  {dest_line}\n"
        f"⚡ انتقال خودکار  ·  <b>{auto_line}</b>\n"
        f"🤖 پردازش هوشمند  ·  <b>{ai_line}</b>\n"
        f"✍️ امضا  ·  <b>{'فعال' if signature_enabled else 'بدون امضا'}</b>\n"
        f"🧩 تنظیم کانال‌ها  ·  <b>{_state_badge(ready, 'کامل')}</b>"
        f"{review_badge}"
        f"</blockquote>\n\n"
        f"📈 <b>{total_forwarded:,}</b> پیام با موفقیت منتقل شده\n\n"
        f"<b>قدم بعدی</b>\n{next_step}"
    )
