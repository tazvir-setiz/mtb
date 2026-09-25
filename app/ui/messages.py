from __future__ import annotations

from html import escape as _e

UNAUTHORIZED = "🔒 <b>دسترسی غیرمجاز</b>\n\nشما اجازه استفاده از این ربات را ندارید."

DIVIDER = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"


def dashboard(
    source_title: str | None,
    destination_title: str | None,
    total_forwarded: int,
    auto_forward_enabled: bool = False,
) -> str:
    source_line = f"✅ <b>{_e(source_title)}</b>" if source_title else "❌ <i>تنظیم نشده</i>"
    dest_line = f"✅ <b>{_e(destination_title)}</b>" if destination_title else "❌ <i>تنظیم نشده</i>"
    auto_line = "🟢 روشن" if auto_forward_enabled else "🔴 خاموش"
    return (
        "🤖 <b>Telegram Forwarder</b>\n"
        f"{DIVIDER}\n\n"
        f"📥 <b>کانال مبدأ</b>\n{source_line}\n\n"
        f"📤 <b>کانال مقصد</b>\n{dest_line}\n\n"
        f"🆕 <b>Auto-Forward</b>\n{auto_line}\n\n"
        f"📊 <b>پیام‌های منتقل‌شده</b>\n<code>{total_forwarded:,}</code>"
    )


def ask_channel(kind: str, current_title: str | None) -> str:
    label = "📥 <b>کانال مبدأ</b>" if kind == "source" else "📤 <b>کانال مقصد</b>"
    current = f"✅ {_e(current_title)}" if current_title else "❌ <i>تنظیم نشده</i>"
    return (
        f"{label}\n\n"
        f"کانال فعلی:\n{current}\n\n"
        f"{DIVIDER}\n\n"
        "🔗 شناسه یا Username کانال را ارسال کنید:\n\n"
        "• <code>@source_channel</code>\n"
        "• <code>-1001234567890</code>"
    )


def channel_confirmed(kind: str, title: str, telegram_id: int, username: str | None) -> str:
    label = "کانال مبدأ" if kind == "source" else "کانال مقصد"
    username_line = f"@{_e(username)}" if username else "—"
    return (
        f"✅ <b>{label} تنظیم شد</b>\n"
        f"{DIVIDER}\n\n"
        f"📢 نام\n<b>{_e(title)}</b>\n\n"
        f"🆔 ID\n<code>{telegram_id}</code>\n\n"
        f"👤 Username\n{username_line}"
    )


PERMISSION_ERROR = (
    "⚠️ <b>دسترسی کافی نیست</b>\n\n"
    "ربات باید در کانال مقصد Administrator باشد\n"
    "و دسترسی لازم برای ارسال پیام را داشته باشد."
)

CHANNEL_NOT_FOUND = "⚠️ کانال یافت نشد یا دسترسی به آن ممکن نیست. شناسه یا Username را بررسی کنید."


def transfer_menu_text(source_title: str, destination_title: str) -> str:
    return (
        "🚀 <b>انتقال پیام‌ها</b>\n"
        f"{DIVIDER}\n\n"
        f"📥 مبدأ:  <b>{_e(source_title)}</b>\n"
        f"📤 مقصد:  <b>{_e(destination_title)}</b>"
    )


def ask_start_id() -> str:
    return "🔢 <b>Message ID شروع</b> را وارد کنید:"


def ask_end_id() -> str:
    return "🔢 <b>Message ID پایان</b> را وارد کنید:"


def range_summary_text(source_title: str, destination_title: str, start_id: int, end_id: int) -> str:
    count = end_id - start_id + 1
    return (
        "📋 <b>خلاصه عملیات</b>\n"
        f"{DIVIDER}\n\n"
        f"📥 مبدأ:  <b>{_e(source_title)}</b>\n"
        f"📤 مقصد:  <b>{_e(destination_title)}</b>\n\n"
        f"🔢 بازه:  <code>{start_id} → {end_id}</code>\n"
        f"📨 تعداد:  <b>{count:,}</b> پیام"
    )


def confirm_transfer_text(count: int, source_title: str, destination_title: str) -> str:
    return (
        "⚠️ <b>تأیید انتقال</b>\n"
        f"{DIVIDER}\n\n"
        f"شما در حال انتقال <b>{count:,}</b> پیام هستید.\n\n"
        f"📥 از:  <b>{_e(source_title)}</b>\n"
        f"📤 به:  <b>{_e(destination_title)}</b>\n\n"
        "آیا مطمئن هستید؟"
    )


def _progress_bar(percent: int, width: int = 12) -> str:
    filled = int(width * percent / 100)
    return "▰" * filled + "▱" * (width - filled)


def progress_text(processed: int, total: int, success: int, skipped: int, failed: int, elapsed_seconds: int) -> str:
    percent = int((processed / total) * 100) if total else 0
    minutes, seconds = divmod(elapsed_seconds, 60)
    return (
        "🚀 <b>در حال انتقال...</b>\n\n"
        f"<code>{_progress_bar(percent)}</code>  <b>{percent}%</b>\n"
        f"{DIVIDER}\n\n"
        f"📨 پردازش:  <b>{processed}</b> / {total}\n"
        f"✅ موفق:  <b>{success}</b>\n"
        f"⏭ تکراری:  <b>{skipped}</b>\n"
        f"❌ خطا:  <b>{failed}</b>\n\n"
        f"⏱ زمان:  <code>{minutes:02d}:{seconds:02d}</code>"
    )


def paused_text(processed: int, total: int, success: int, failed: int) -> str:
    return (
        "⏸ <b>عملیات متوقف شد</b>\n"
        f"{DIVIDER}\n\n"
        f"📨 پردازش:  <b>{processed}</b> / {total}\n"
        f"✅ موفق:  <b>{success}</b>\n"
        f"❌ خطا:  <b>{failed}</b>"
    )


def flood_wait_text(seconds: int) -> str:
    return (
        "⏳ <b>محدودیت Telegram</b>\n\n"
        f"برای ادامه عملیات باید <b>{seconds}</b> ثانیه صبر کنیم.\n\n"
        "ربات به‌صورت خودکار ادامه خواهد داد."
    )


def final_result_text(total: int, success: int, skipped: int, failed: int, elapsed_seconds: int) -> str:
    minutes, seconds = divmod(elapsed_seconds, 60)
    return (
        "🎉 <b>انتقال به پایان رسید</b>\n"
        f"{DIVIDER}\n\n"
        f"📨 کل:  <b>{total:,}</b>\n"
        f"✅ موفق:  <b>{success:,}</b>\n"
        f"⏭ تکراری:  <b>{skipped:,}</b>\n"
        f"❌ ناموفق:  <b>{failed:,}</b>\n\n"
        f"⏱ زمان:  <code>{minutes:02d}:{seconds:02d}</code>\n"
        f"{DIVIDER}"
    )


def failed_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "❌ <b>پیام‌های ناموفق</b>\n\n<i>موردی یافت نشد.</i>"
    lines = ["❌ <b>پیام‌های ناموفق</b>", DIVIDER, ""]
    for msg_id, error in items:
        lines.append(f"<code>#{msg_id}</code>  ⚠️ {_e(error)}")
    return "\n".join(lines)


def recent_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "📋 <b>پیام‌های اخیر</b>\n\n<i>هنوز پیامی منتقل نشده است.</i>"
    lines = ["📋 <b>پیام‌های اخیر</b>", DIVIDER, ""]
    for msg_id, status_icon in items:
        lines.append(f"<code>#{msg_id}</code>  {status_icon}")
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
        "📊 <b>آمار</b>\n"
        f"{DIVIDER}\n\n"
        f"📨 کل پردازش:  <b>{total:,}</b>\n"
        f"✅ موفق:  <b>{success:,}</b>\n"
        f"❌ خطا:  <b>{failed:,}</b>\n"
        f"⏭ تکراری:  <b>{duplicate:,}</b>\n\n"
        f"📥 مبدأ:  <b>{_e(source_title)}</b>\n"
        f"📤 مقصد:  <b>{_e(destination_title)}</b>\n\n"
        f"🕐 آخرین عملیات:  <code>{_e(last_operation)}</code>"
    )


HELP_TEXT = (
    "❓ <b>راهنما</b>\n"
    f"{DIVIDER}\n\n"
    "این ربات پیام‌ها را به‌صورت Forward واقعی از یک کانال مبدأ به کانال مقصد منتقل می‌کند.\n\n"
    "1️⃣ ابتدا <b>کانال مبدأ</b> را تنظیم کنید (ربات باید عضو آن باشد).\n"
    "2️⃣ سپس <b>کانال مقصد</b> را تنظیم کنید (ربات باید Administrator باشد).\n"
    "3️⃣ از منوی «انتقال پیام‌ها» بازه یا شناسه پیام‌ها را مشخص کنید، یا "
    "<b>Auto-Forward</b> را از داشبورد روشن کنید تا پیام‌های جدید خودکار منتقل شوند.\n"
    "4️⃣ عملیات دستی را تأیید کنید تا Forward آغاز شود."
)
