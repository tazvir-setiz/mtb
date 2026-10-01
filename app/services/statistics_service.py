from __future__ import annotations

from app.database.database import get_session
from app.database.models import ChannelType, ForwardJob
from app.database.repository import ChannelRepository, ForwardedMessageRepository
from app.utils.helpers import format_datetime


def get_statistics_text() -> str:
    from sqlalchemy import select

    from app.ui import messages as ui_messages

    with get_session() as session:
        stats = ForwardedMessageRepository.stats(session)
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)
        last_job = (
            session.execute(select(ForwardJob).order_by(ForwardJob.id.desc())).scalars().first()
        )

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
    )


def clear_statistics() -> None:
    from app.database.repository import SettingsRepository

    with get_session() as session:
        SettingsRepository.clear_all_data(session)


def get_recent_messages(limit: int = 10) -> list[tuple[int, str]]:
    from app.utils.helpers import status_icon

    with get_session() as session:
        records = ForwardedMessageRepository.recent(session, limit=limit)
    return [
        (
            f"{r.source_channel_id}/{r.source_message_id} → {r.destination_channel_id}",
            status_icon(r.status),
        )
        for r in records
    ]
