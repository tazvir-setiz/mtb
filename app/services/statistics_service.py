from __future__ import annotations

import logging
import time
from sqlalchemy import func, select, text

from app.config import settings
from app.database.database import get_session
from app.database.models import Channel, ChannelType, ForwardedMessage, ForwardJob, MessageStatus, ReviewRequest
from app.database.repository import ChannelRepository, ForwardedMessageRepository, SettingsRepository
from app.services.ai_settings import load_ai_settings
from app.telegram import auto_forward
from app.telegram.client import get_client
from app.utils.helpers import format_datetime, status_icon

logger = logging.getLogger(__name__)


def get_statistics_text() -> str:
    from app.ui import messages as ui_messages

    with get_session() as session:
        stats = ForwardedMessageRepository.stats(session)
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)
        last_job = (
            session.execute(select(ForwardJob).order_by(ForwardJob.id.desc())).scalars().first()
        )

        pending_reviews = (
            session.query(func.count(ReviewRequest.id))
            .filter(ReviewRequest.status.in_(["pending", "sending", "uncertain"]))
            .scalar()
            or 0
        )
        rejected_reviews = (
            session.query(func.count(ReviewRequest.id))
            .filter(ReviewRequest.status == "rejected")
            .scalar()
            or 0
        )
        approved_reviews = (
            session.query(func.count(ReviewRequest.id))
            .filter(ReviewRequest.status == "approved")
            .scalar()
            or 0
        )

    auto_stats = auto_forward.status_snapshot()

    return ui_messages.statistics_text(
        total=stats["total"],
        success=stats["success"],
        failed=stats["failed"],
        duplicate=stats["duplicate"],
        source_title=f"مبداها: {len(sources)}",
        destination_title=f"مقصدها: {len(destinations)}",
        last_operation=format_datetime(last_job.finished_at or last_job.started_at)
        if last_job
        else "—",
        pending_reviews=pending_reviews,
        rejected_reviews=rejected_reviews,
        approved_reviews=approved_reviews,
        auto_stats=auto_stats,
    )


def clear_statistics() -> None:
    with get_session() as session:
        SettingsRepository.clear_all_data(session)


def get_recent_messages(limit: int = 10) -> list[dict]:
    with get_session() as session:
        records = ForwardedMessageRepository.recent(session, limit=limit)
        channels = {c.telegram_id: c.title for c in session.query(Channel).all()}

        items: list[dict] = []
        for r in records:
            src_title = channels.get(r.source_channel_id, str(r.source_channel_id))
            dst_title = channels.get(r.destination_channel_id, str(r.destination_channel_id))

            review = (
                session.query(ReviewRequest)
                .filter(
                    ReviewRequest.source_id == r.source_channel_id,
                    ReviewRequest.message_id == r.source_message_id,
                )
                .order_by(ReviewRequest.id.desc())
                .first()
            )

            status_map = {
                MessageStatus.SUCCESS: "ارسال شد",
                MessageStatus.FAILED: "ناموفق",
                MessageStatus.DUPLICATE: "تکراری (رد شد)",
                MessageStatus.SKIPPED: "رد شد",
            }
            status_desc = status_map.get(r.status, "نامشخص")

            reason = None
            preview = None
            if review:
                preview = (review.preview or "").strip()[:60]
                reason = review.reason
            elif r.error:
                reason = r.error[:80]

            items.append(
                {
                    "icon": status_icon(r.status),
                    "source": src_title,
                    "destination": dst_title,
                    "message_id": r.source_message_id,
                    "time": format_datetime(r.created_at),
                    "status_text": status_desc,
                    "preview": preview,
                    "reason": reason,
                }
            )

    return items


async def get_system_health_report() -> str:
    # 1. Telegram Client Health
    client_status_lines = []
    try:
        client = get_client()
        t0 = time.monotonic()
        connected = client.is_connected()
        if not connected:
            try:
                await client.connect()
                connected = client.is_connected()
            except Exception:
                connected = False

        if connected:
            authorized = await client.is_user_authorized()
            if authorized:
                me = await client.get_me()
                latency_ms = (time.monotonic() - t0) * 1000
                account_name = getattr(me, "first_name", "کاربر")
                username = f"@{me.username}" if getattr(me, "username", None) else str(getattr(me, "id", ""))
                client_status_lines.append(f"• وضعیت: <b>🟢 متصل و آماده</b>")
                client_status_lines.append(f"• حساب: <b>{account_name}</b> ({username})")
                client_status_lines.append(f"• تأخیر رفت‌وبرگشت: <code>{latency_ms:.1f}ms</code>")
            else:
                client_status_lines.append("• وضعیت: <b>⚠️ سشن لاگین نیست (نیاز به auth)</b>")
        else:
            client_status_lines.append("• وضعیت: <b>🔴 قطع اتصال (بررسی اینترنت یا پروکسی)</b>")
    except Exception as exc:
        client_status_lines.append(f"• وضعیت: <b>❌ خطای کلاینت: {exc.__class__.__name__}</b>")

    # 2. Database Health
    db_status_lines = []
    try:
        t_db = time.monotonic()
        with get_session() as session:
            session.execute(text("SELECT 1"))
            db_ms = (time.monotonic() - t_db) * 1000
            dialect = session.bind.dialect.name if session.bind else "unknown"
            engine_desc = "PostgreSQL" if dialect == "postgresql" else "SQLite (WAL)"
            db_status_lines.append(f"• وضعیت: <b>🟢 متصل و پایدار</b>")
            db_status_lines.append(f"• موتور: <b>{engine_desc}</b>")
            db_status_lines.append(f"• تأخیر کوئری: <code>{db_ms:.2f}ms</code>")
    except Exception as exc:
        db_status_lines.append(f"• وضعیت: <b>❌ خطا در دیتابیس: {exc.__class__.__name__}</b>")

    # 3. AI Guard Health
    ai_status_lines = []
    ai_cfg = load_ai_settings(settings)
    if ai_cfg.enabled:
        key_status = "✅ ثبت شده" if ai_cfg.api_key else "⚠️ کلید ثبت نشده"
        ai_status_lines.append(f"• وضعیت گارد: <b>🟢 فعال</b>")
        ai_status_lines.append(f"• مدل فعال: <code>{ai_cfg.model}</code>")
        ai_status_lines.append(f"• کلید API: <b>{key_status}</b>")
        ai_status_lines.append(f"• سرویس: <code>{ai_cfg.base_url}</code>")
    else:
        ai_status_lines.append("• وضعیت گارد: <b>⚪ غیرفعال (پالایش خاموش است)</b>")

    # 4. Auto-Forwarding Runtime Snapshot
    snap = auto_forward.status_snapshot()
    auto_status_lines = [
        f"• شنود زنده پیام‌ها: <b>{'🟢 فعال' if snap.get('listener_active') else '⚪ خاموش'}</b>",
        f"• پیام‌های در انتظار صف: <b>{snap.get('waiting', 0)}</b>",
        f"• اسلات‌های در حال پردازش: <b>{'فعال' if snap.get('processing') else 'آزاد'}</b>",
        f"• کل دریافتی این سشن: <b>{snap.get('received', 0):,}</b>",
        f"• ارسالی موفق این سشن: <b>{snap.get('sent', 0):,}</b>",
    ]

    now_str = format_datetime(None)
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return (
        "🩺 <b>گزارش تست سلامت سیستم (Diagnostics)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 <b>کلاینت تلگرام (Telethon):</b>\n"
        + "\n".join(client_status_lines)
        + "\n\n🗄 <b>پایگاه داده:</b>\n"
        + "\n".join(db_status_lines)
        + "\n\n🤖 <b>موتور هوش مصنوعی (AI Guard):</b>\n"
        + "\n".join(ai_status_lines)
        + "\n\n⚡ <b>سرویس انتقال خودکار:</b>\n"
        + "\n".join(auto_status_lines)
        + f"\n\n🕒 زمان بررسی: <code>{now_str}</code>"
    )
