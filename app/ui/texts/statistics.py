from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER


def recent_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "🕘 <b>پیام‌های اخیر</b>\n\n<i>هنوز پیامی ثبت نشده است.</i>"

    lines = ["🕘 <b>پیام‌های اخیر</b>", DIVIDER, ""]
    for msg_id, status_icon in items:
        lines.append(f"{status_icon}  <code>#{msg_id}</code>")
    return "\n".join(lines)


def statistics_text(
    total: int,
    success: int,
    failed: int,
    duplicate: int,
    source_title: str,
    destination_title: str,
    last_operation: str,
) -> str:
    success_rate = (success / total * 100) if total else 0.0

    return (
        "📊 <b>آمار انتقال</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📨 کل پردازش  <b>{total:,}</b>\n"
        f"✅ موفق  <b>{success:,}</b>\n"
        f"❌ خطا  <b>{failed:,}</b>\n"
        f"⏭ تکراری  <b>{duplicate:,}</b>\n"
        f"🎯 نرخ موفقیت  <b>{success_rate:.1f}%</b>"
        "</blockquote>\n\n"
        f"📥 <b>{_e(source_title)}</b>\n"
        f"📤 <b>{_e(destination_title)}</b>\n"
        f"🕐 آخرین عملیات: <code>{_e(last_operation)}</code>"
    )


def clear_statistics_confirm_text() -> str:
    return (
        "🗑 <b>پاک کردن آمار؟</b>\n\n"
        "سوابق عملیات و پیام‌های ثبت‌شده حذف می‌شوند.\n"
        "<b>این کار قابل بازگشت نیست.</b>"
    )
