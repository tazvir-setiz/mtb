from __future__ import annotations

UNAUTHORIZED = "🔒 دسترسی غیرمجاز\n\nشما اجازه استفاده از این ربات را ندارید."


def dashboard(source_title: str | None, destination_title: str | None, total_forwarded: int) -> str:
    source_line = f"✅ {source_title}" if source_title else "❌ تنظیم نشده"
    dest_line = f"✅ {destination_title}" if destination_title else "❌ تنظیم نشده"
    return (
        "🤖 Telegram Forwarder\n\n"
        "🟢 وضعیت: آماده\n\n"
        f"📥 کانال مبدأ:\n{source_line}\n\n"
        f"📤 کانال مقصد:\n{dest_line}\n\n"
        f"📊 پیام‌های منتقل‌شده:\n{total_forwarded}"
    )


def ask_channel(kind: str, current_title: str | None) -> str:
    label = "📥 کانال مبدأ" if kind == "source" else "📤 کانال مقصد"
    current = f"✅ {current_title}" if current_title else "❌ تنظیم نشده"
    return (
        f"{label}\n\n"
        f"کانال فعلی:\n{current}\n\n"
        "شناسه یا Username کانال را ارسال کنید.\n\n"
        "مثال:\n@source_channel\nیا:\n-1001234567890"
    )


def channel_confirmed(kind: str, title: str, telegram_id: int, username: str | None) -> str:
    label = "کانال مبدأ" if kind == "source" else "کانال مقصد"
    username_line = f"@{username}" if username else "—"
    return (
        f"✅ {label} تنظیم شد\n\n"
        f"📢 نام:\n{title}\n\n"
        f"🆔 ID:\n{telegram_id}\n\n"
        f"👤 Username:\n{username_line}"
    )


PERMISSION_ERROR = (
    "⚠️ دسترسی کافی نیست\n\n"
    "ربات باید در کانال مقصد Administrator باشد\n"
    "و دسترسی لازم برای ارسال پیام را داشته باشد."
)

CHANNEL_NOT_FOUND = "⚠️ کانال یافت نشد یا دسترسی به آن ممکن نیست. شناسه یا Username را بررسی کنید."


def transfer_menu_text(source_title: str, destination_title: str) -> str:
    return (
        "🚀 انتقال پیام‌ها\n\n"
        f"📥 مبدأ:\n{source_title}\n\n"
        f"📤 مقصد:\n{destination_title}"
    )


def ask_start_id() -> str:
    return "🔢 Message ID شروع را وارد کنید:"


def ask_end_id() -> str:
    return "🔢 Message ID پایان را وارد کنید:"


def range_summary_text(source_title: str, destination_title: str, start_id: int, end_id: int) -> str:
    count = end_id - start_id + 1
    return (
        "📋 خلاصه عملیات\n\n"
        f"📥 مبدأ:\n{source_title}\n\n"
        f"📤 مقصد:\n{destination_title}\n\n"
        f"🔢 بازه:\n{start_id} → {end_id}\n\n"
        f"📨 تعداد:\n{count} پیام"
    )


def confirm_transfer_text(count: int, source_title: str, destination_title: str) -> str:
    return (
        "⚠️ تأیید انتقال\n\n"
        f"شما در حال انتقال {count} پیام هستید.\n\n"
        f"📥 از:\n{source_title}\n\n"
        f"📤 به:\n{destination_title}\n\n"
        "آیا مطمئن هستید؟"
    )


def _progress_bar(percent: int, width: int = 12) -> str:
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


def progress_text(processed: int, total: int, success: int, skipped: int, failed: int, elapsed_seconds: int) -> str:
    percent = int((processed / total) * 100) if total else 0
    minutes, seconds = divmod(elapsed_seconds, 60)
    return (
        "🚀 در حال انتقال...\n\n"
        f"{_progress_bar(percent)} {percent}%\n\n"
        f"📨 پردازش:\n{processed} / {total}\n\n"
        f"✅ موفق:\n{success}\n\n"
        f"⏭ تکراری:\n{skipped}\n\n"
        f"❌ خطا:\n{failed}\n\n"
        f"⏱ زمان:\n{minutes:02d}:{seconds:02d}"
    )


def paused_text(processed: int, total: int, success: int, failed: int) -> str:
    return (
        "⏸ عملیات متوقف شد\n\n"
        f"📨 پردازش:\n{processed} / {total}\n\n"
        f"✅ موفق:\n{success}\n\n"
        f"❌ خطا:\n{failed}"
    )


def flood_wait_text(seconds: int) -> str:
    return (
        "⏳ محدودیت Telegram\n\n"
        f"برای ادامه عملیات باید {seconds} ثانیه صبر کنیم.\n\n"
        "ربات به‌صورت خودکار ادامه خواهد داد."
    )


def final_result_text(total: int, success: int, skipped: int, failed: int, elapsed_seconds: int) -> str:
    minutes, seconds = divmod(elapsed_seconds, 60)
    return (
        "🎉 انتقال به پایان رسید\n\n"
        "━━━━━━━━━━━━━━━━\n\n"
        f"📨 کل:\n{total}\n\n"
        f"✅ موفق:\n{success}\n\n"
        f"⏭ تکراری:\n{skipped}\n\n"
        f"❌ ناموفق:\n{failed}\n\n"
        f"⏱ زمان:\n{minutes:02d}:{seconds:02d}\n\n"
        "━━━━━━━━━━━━━━━━"
    )


def failed_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "❌ پیام‌های ناموفق\n\nموردی یافت نشد."
    lines = ["❌ پیام‌های ناموفق\n"]
    for msg_id, error in items:
        lines.append(f"Message #{msg_id}\n⚠️ {error}\n")
    return "\n".join(lines)


def recent_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "📋 پیام‌های اخیر\n\nهنوز پیامی منتقل نشده است."
    lines = ["📋 پیام‌های اخیر\n"]
    for msg_id, status_icon in items:
        lines.append(f"📨 #{msg_id}  {status_icon}")
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
    return (
        "📊 آمار\n\n"
        f"📨 کل پردازش:\n{total:,}\n\n"
        f"✅ موفق:\n{success:,}\n\n"
        f"❌ خطا:\n{failed:,}\n\n"
        f"⏭ تکراری:\n{duplicate:,}\n\n"
        f"📥 مبدأ:\n{source_title}\n\n"
        f"📤 مقصد:\n{destination_title}\n\n"
        f"🕐 آخرین عملیات:\n{last_operation}"
    )


HELP_TEXT = (
    "❓ راهنما\n\n"
    "این ربات پیام‌ها را به‌صورت Forward واقعی از یک کانال مبدأ به کانال مقصد منتقل می‌کند.\n\n"
    "۱. ابتدا کانال مبدأ را تنظیم کنید (ربات باید عضو آن باشد).\n"
    "۲. سپس کانال مقصد را تنظیم کنید (ربات باید Administrator باشد).\n"
    "۳. از منوی «انتقال پیام‌ها» بازه یا شناسه پیام‌ها را مشخص کنید.\n"
    "۴. عملیات را تأیید کنید تا Forward آغاز شود."
)
