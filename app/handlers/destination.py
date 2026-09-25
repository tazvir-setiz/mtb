"""
منطق کانال مقصد به‌طور مشترک با کانال مبدأ در app.handlers.source پیاده‌سازی شده
(چون هر دو یک جریان یکسان دارند: دریافت -> اعتبارسنجی -> ذخیره -> تأیید).
این ماژول صرفاً برای رعایت ساختار پروژه، توابع مرتبط با مقصد را دوباره صادر می‌کند.
"""
from __future__ import annotations

from app.handlers.source import (  # noqa: F401
    handle_change,
    handle_confirm,
    handle_destination_help,
    handle_destination_retry,
    show_channel_prompt,
)
