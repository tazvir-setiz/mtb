from __future__ import annotations

from html import escape as _e

from app.ui.texts.common import DIVIDER


def transfer_menu_text(source_title: str, destination_title: str) -> str:
    return (
        "🚀 <b>انتقال پیام‌ها</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📥 <b>{_e(source_title)}</b>\n"
        f"            ↓\n"
        f"📤 <b>{_e(destination_title)}</b>"
        "</blockquote>\n\n"
        "روش انتقال را انتخاب کنید:\n"
        "• <b>بازه</b> برای پیام‌های پشت‌سرهم\n"
        "• <b>Message ID</b> برای چند پیام مشخص"
    )


def ask_start_id() -> str:
    return (
        "🔢 <b>Message ID شروع</b>\n\n"
        "شماره اولین پیام بازه را ارسال کنید.\n"
        "<i>مثال: <code>1200</code></i>"
    )


def ask_end_id() -> str:
    return (
        "🔢 <b>Message ID پایان</b>\n\n"
        "شماره آخرین پیام بازه را ارسال کنید.\n"
        "<i>این مقدار باید بزرگ‌تر یا مساوی ID شروع باشد.</i>"
    )


def range_summary_text(
    source_title: str, destination_title: str, start_id: int, end_id: int
) -> str:
    count = end_id - start_id + 1
    return (
        "🧾 <b>خلاصه بازه</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📥 {_e(source_title)}\n"
        f"📤 {_e(destination_title)}\n"
        f"🔢 <code>{start_id} → {end_id}</code>\n"
        f"📨 <b>{count:,}</b> پیام"
        "</blockquote>\n\n"
        "در مرحله بعد، تأیید نهایی انجام می‌شود."
    )


def confirm_transfer_text(count: int, source_title: str, destination_title: str) -> str:
    return (
        "⚠️ <b>تأیید نهایی انتقال</b>\n"
        f"{DIVIDER}\n\n"
        f"قرار است <b>{count:,}</b> پیام منتقل شود.\n\n"
        "<blockquote>"
        f"📥 از: <b>{_e(source_title)}</b>\n"
        f"📤 به: <b>{_e(destination_title)}</b>"
        "</blockquote>\n\n"
        "با شروع عملیات، وضعیت پیشرفت در همین پیام به‌روزرسانی می‌شود."
    )


def _progress_bar(percent: int, width: int = 12) -> str:
    filled = min(width, max(0, round(width * percent / 100)))
    return "▰" * filled + "▱" * (width - filled)


def progress_text(
    processed: int,
    total: int,
    success: int,
    skipped: int,
    failed: int,
    elapsed_seconds: int,
) -> str:
    percent = int((processed / total) * 100) if total else 0
    minutes, seconds = divmod(elapsed_seconds, 60)

    return (
        "⚡ <b>انتقال در حال اجراست</b>\n\n"
        f"<code>{_progress_bar(percent)}</code>  <b>{percent}%</b>\n\n"
        "<blockquote>"
        f"📨 پردازش‌شده  <b>{processed:,}</b> / {total:,}\n"
        f"✅ موفق  <b>{success:,}</b>\n"
        f"⏭ ردشده/تکراری  <b>{skipped:,}</b>\n"
        f"❌ خطا  <b>{failed:,}</b>\n"
        f"⏱ زمان  <code>{minutes:02d}:{seconds:02d}</code>"
        "</blockquote>"
    )


def paused_text(processed: int, total: int, success: int, failed: int) -> str:
    percent = int((processed / total) * 100) if total else 0
    return (
        "⏸ <b>انتقال متوقف شده</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📊 پیشرفت  <b>{percent}%</b>\n"
        f"📨 پردازش  <b>{processed:,}</b> / {total:,}\n"
        f"✅ موفق  <b>{success:,}</b>\n"
        f"❌ خطا  <b>{failed:,}</b>"
        "</blockquote>\n\n"
        "می‌توانید عملیات را ادامه دهید یا از ابتدا شروع کنید."
    )


def flood_wait_text(seconds: int) -> str:
    return (
        "⏳ <b>محدودیت موقت Telegram</b>\n\n"
        f"Telegram درخواست کرده <b>{seconds}</b> ثانیه مکث شود.\n"
        "عملیات بعد از پایان محدودیت به‌صورت خودکار ادامه پیدا می‌کند."
    )


def final_result_text(
    total: int, success: int, skipped: int, failed: int, elapsed_seconds: int
) -> str:
    minutes, seconds = divmod(elapsed_seconds, 60)
    success_rate = (success / total * 100) if total else 0.0

    return (
        "✅ <b>انتقال به پایان رسید</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📨 کل  <b>{total:,}</b>\n"
        f"✅ موفق  <b>{success:,}</b>\n"
        f"⏭ ردشده/تکراری  <b>{skipped:,}</b>\n"
        f"❌ ناموفق  <b>{failed:,}</b>\n"
        f"🎯 نرخ موفقیت  <b>{success_rate:.1f}%</b>\n"
        f"⏱ زمان  <code>{minutes:02d}:{seconds:02d}</code>"
        "</blockquote>"
    )


def failed_messages_text(items: list[tuple[int, str]]) -> str:
    if not items:
        return "✅ <b>پیام ناموفقی وجود ندارد</b>"

    lines = ["⚠️ <b>پیام‌های ناموفق</b>", DIVIDER, ""]
    for msg_id, error in items:
        lines.append(f"<code>#{msg_id}</code>  ·  {_e(error)}")
    return "\n".join(lines)
