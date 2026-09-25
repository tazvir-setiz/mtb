from __future__ import annotations

from html import escape as _e

UNAUTHORIZED = "🔒 <b>دسترسی غیرمجاز</b>\n\nاین پنل فقط برای مدیران مجاز فعال است."

BOT_SHORT_DESCRIPTION = "پنل مدیریت انتقال پیام بین کانال‌ها، Auto-Forward و گزارش عملیات."
BOT_DESCRIPTION = (
    "Telegram Forwarder یک پنل مدیریتی برای تنظیم کانال مبدأ و مقصد، انتقال بازه‌ای "
    "یا انتخابی پیام‌ها، Auto-Forward، مشاهده آمار و مدیریت امضای پیام‌هاست."
)

DIVIDER = "━━━━━━━━━━━━━━━━━━"


def _state_badge(enabled: bool, yes: str = "آماده", no: str = "تنظیم نشده") -> str:
    return f"✅ {yes}" if enabled else f"⚠️ {no}"


def dashboard(
    source_title: str | None,
    destination_title: str | None,
    total_forwarded: int,
    auto_forward_enabled: bool = False,
) -> str:
    source_line = f"✅ <b>{_e(source_title)}</b>" if source_title else "⚠️ <i>تنظیم نشده</i>"
    dest_line = (
        f"✅ <b>{_e(destination_title)}</b>"
        if destination_title
        else "⚠️ <i>تنظیم نشده</i>"
    )
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


def ask_channel(kind: str, current_title: str | None) -> str:
    label = "📥 <b>کانال مبدأ</b>" if kind == "source" else "📤 <b>کانال مقصد</b>"
    current = f"✅ <b>{_e(current_title)}</b>" if current_title else "⚠️ <i>تنظیم نشده</i>"
    permission_hint = (
        "ربات/کلاینت متصل باید به کانال دسترسی خواندن داشته باشد."
        if kind == "source"
        else "در مقصد، دسترسی ارسال پیام لازم است."
    )

    return (
        f"{label}\n"
        f"{DIVIDER}\n\n"
        f"کانال فعلی: {current}\n\n"
        "شناسه، Username یا لینک کانال را ارسال کنید.\n\n"
        "<blockquote>"
        "<code>@channel_username</code>\n"
        "<code>-1001234567890</code>\n"
        "<code>https://t.me/channel_username</code>"
        "</blockquote>\n"
        f"<i>{permission_hint}</i>"
    )


def channel_confirmed(kind: str, title: str, telegram_id: int, username: str | None) -> str:
    label = "مبدأ" if kind == "source" else "مقصد"
    username_line = f"@{_e(username)}" if username else "—"

    return (
        f"✅ <b>کانال {label} شناسایی شد</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"📢 <b>{_e(title)}</b>\n"
        f"🆔 <code>{telegram_id}</code>\n"
        f"👤 {username_line}"
        "</blockquote>\n\n"
        "اطلاعات را بررسی و تأیید کنید."
    )


PERMISSION_ERROR = (
    "🛡 <b>دسترسی مقصد کامل نیست</b>\n\n"
    "ربات یا حساب متصل باید در کانال مقصد Administrator باشد و اجازه ارسال پیام داشته باشد."
)

CHANNEL_NOT_FOUND = (
    "⚠️ <b>کانال پیدا نشد</b>\n\n"
    "شناسه، Username یا لینک را بررسی کنید و مطمئن شوید حساب متصل به کانال دسترسی دارد."
)


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


def range_summary_text(source_title: str, destination_title: str, start_id: int, end_id: int) -> str:
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


def final_result_text(total: int, success: int, skipped: int, failed: int, elapsed_seconds: int) -> str:
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


HELP_TEXT = (
    "❓ <b>راهنمای Forwarder</b>\n"
    f"{DIVIDER}\n\n"
    "برای شروع فقط سه مرحله لازم است:\n\n"
    "1️⃣ کانال <b>مبدأ</b> را تنظیم کنید.\n"
    "2️⃣ کانال <b>مقصد</b> را تنظیم و دسترسی ارسال را بررسی کنید.\n"
    "3️⃣ انتقال دستی را اجرا کنید یا <b>Auto-Forward</b> را روشن کنید.\n\n"
    "<blockquote expandable>"
    "<b>روش‌های انتقال</b>\n"
    "• بازه Message ID برای پیام‌های پشت‌سرهم\n"
    "• لیست Message ID برای پیام‌های انتخابی\n\n"
    "<b>Auto-Forward</b>\n"
    "پیام‌های جدید مبدأ را به‌صورت خودکار پردازش و ارسال می‌کند.\n\n"
    "<b>نکته</b>\n"
    "کانال مقصد باید مجوز ارسال پیام داشته باشد و تنظیمات AI/امضا در زمان ارسال اعمال می‌شوند."
    "</blockquote>"
)


def settings_text(
    signature: str | None,
    forward_delay: float | None = None,
    ai_enabled: bool | None = None,
) -> str:
    if signature:
        preview = signature.strip()
        if len(preview) > 180:
            preview = preview[:177] + "..."
        signature_line = f"✅ تنظیم شده\n<code>{_e(preview)}</code>"
    else:
        signature_line = "⚪ تنظیم نشده"

    delay_line = f"{forward_delay:g} ثانیه" if forward_delay is not None else "—"
    ai_line = (
        "🟢 فعال"
        if ai_enabled is True
        else "⚪ غیرفعال"
        if ai_enabled is False
        else "—"
    )

    return (
        "⚙️ <b>تنظیمات</b>\n"
        f"{DIVIDER}\n\n"
        "<blockquote>"
        f"⏱ فاصله ارسال  <b>{delay_line}</b>\n"
        f"🧠 AI Guardrails  <b>{ai_line}</b>\n"
        f"✍️ امضا  {signature_line}"
        "</blockquote>\n\n"
        "<i>تنظیمات حساس با تأیید دوباره اعمال می‌شوند.</i>"
    )


def ask_signature() -> str:
    return (
        "✍️ <b>امضا / زیرنویس</b>\n\n"
        "متنی را که باید زیر پیام‌های منتقل‌شده قرار بگیرد ارسال کنید.\n"
        "فرمت‌های Telegram مثل <b>Bold</b>، <i>Italic</i> و لینک حفظ می‌شوند.\n\n"
        "<blockquote>"
        "برای رسانه‌ها، محدودیت طول Caption تلگرام را در نظر بگیرید."
        "</blockquote>"
    )


def clear_data_confirm_text() -> str:
    return (
        "🗑 <b>پاک کردن داده‌های عملیات؟</b>\n\n"
        "تاریخچه Jobها و پیام‌های ثبت‌شده حذف می‌شود، اما تنظیم کانال‌ها و امضا باقی می‌ماند.\n\n"
        "<b>این عملیات قابل بازگشت نیست.</b>"
    )
