from __future__ import annotations

UNAUTHORIZED = "🔒 <b>دسترسی غیرمجاز</b>\n\nاین پنل فقط برای مدیران مجاز فعال است."


BOT_SHORT_DESCRIPTION = "پنل مدیریت انتقال پیام بین کانال‌ها، Auto-Forward و گزارش عملیات."


BOT_DESCRIPTION = (
    "Telegram Forwarder یک پنل مدیریتی برای تنظیم کانال مبدأ و مقصد، انتقال بازه‌ای "
    "یا انتخابی پیام‌ها، Auto-Forward، مشاهده آمار و مدیریت امضای پیام‌هاست."
)


DIVIDER = "━━━━━━━━━━━━━━━━━━"


def _state_badge(enabled: bool, yes: str = "آماده", no: str = "تنظیم نشده") -> str:
    return f"✅ {yes}" if enabled else f"⚠️ {no}"
