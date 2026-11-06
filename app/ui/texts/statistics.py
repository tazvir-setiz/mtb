from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER


def recent_messages_text(items: list[tuple[int, str] | dict]) -> str:
    if not items:
        return "🕘 <b>پیام‌های اخیر</b>\n\n<i>هنوز پیامی ثبت نشده است.</i>"

    lines = ["🕘 <b>گزارش رویدادهای اخیر انتقال</b>", DIVIDER, ""]
    has_rich = any(isinstance(item, dict) for item in items)

    for item in items:
        if isinstance(item, dict):
            reason_part = f"\n   ⚠️ علت: <i>{_e(item['reason'])}</i>" if item.get("reason") else ""
            preview_part = f"\n   💬 <code>{_e(item['preview'])}</code>" if item.get("preview") else ""
            lines.append(
                f"{item['icon']} <b>{_e(item['source'])} ➔ {_e(item['destination'])}</b> (<code>#{item['message_id']}</code>)\n"
                f"   🕒 <i>{item['time']}</i> · وضعیت: <b>{item['status_text']}</b>"
                + preview_part
                + reason_part
            )
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            identifier, icon = item
            lines.append(f"{icon}  <code>#{identifier}</code>")
        else:
            lines.append(f"• {_e(str(item))}")

    sep = "\n\n" if has_rich else "\n"
    return sep.join(lines)


def statistics_text(
    total: int,
    success: int,
    failed: int,
    duplicate: int,
    source_title: str,
    destination_title: str,
    last_operation: str,
    *,
    pending_reviews: int = 0,
    rejected_reviews: int = 0,
    approved_reviews: int = 0,
    auto_stats: dict | None = None,
) -> str:
    success_rate = (success / total * 100) if total else 0.0

    lines = [
        "📊 <b>گزارش جامع آمار و عملکرد</b>",
        f"{DIVIDER}\n",
        "<blockquote>",
        f"📨 کل پردازش: <b>{total:,}</b>",
        f"✅ ارسالی موفق: <b>{success:,}</b>",
        f"🎯 نرخ موفقیت کلی: <b>{success_rate:.1f}%</b>",
        f"⏭ تکراری / رد شده: <b>{duplicate:,}</b>",
        f"❌ خطای ارسال: <b>{failed:,}</b>",
        "</blockquote>\n",
        "🛡 <b>پالایش هوشمند و خطوط قرمز (AI Guard):</b>",
        "<blockquote>",
        f"⏳ در صف بررسی مدیر: <b>{pending_reviews:,} مورد</b>",
        f"🚫 مسدود شده با سیاست محتوا: <b>{rejected_reviews:,} پیام</b>",
        f"✍️ تایید / بازنویسی شده: <b>{approved_reviews:,} پیام</b>",
        "</blockquote>",
    ]

    if auto_stats and auto_stats.get("received", 0) > 0:
        lines.extend(
            [
                "\n⚡ <b>سشن زنده (Auto-Forward):</b>",
                "<blockquote>",
                f"📥 دریافتی در این سشن: <b>{auto_stats.get('received', 0):,}</b>",
                f"📤 ارسالی در این سشن: <b>{auto_stats.get('sent', 0):,}</b>",
                f"⏳ در صف نوبت: <b>{auto_stats.get('waiting', 0)}</b>",
                "</blockquote>",
            ]
        )

    lines.extend(
        [
            f"\n📥 <b>{_e(source_title)}</b>",
            f"📤 <b>{_e(destination_title)}</b>",
            f"🕐 آخرین عملیات: <code>{_e(last_operation)}</code>",
        ]
    )

    return "\n".join(lines)


def clear_statistics_confirm_text() -> str:
    return (
        "🗑 <b>پاک کردن آمار؟</b>\n\n"
        "سوابق عملیات و پیام‌های ثبت‌شده حذف می‌شوند.\n"
        "<b>این کار قابل بازگشت نیست.</b>"
    )
