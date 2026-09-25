from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Channel, ChannelType


class ChannelRepository:
    @staticmethod
    def upsert(
        session: Session,
        telegram_id: int,
        title: str,
        channel_type: ChannelType,
        username: str | None = None,
    ) -> Channel:
        existing = session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id, Channel.type == channel_type)
        ).scalar_one_or_none()
        if existing:
            existing.title = title
            existing.username = username
            existing.updated_at = datetime.utcnow()
            session.flush()
            return existing

        # هر نوع کانال (مبدأ/مقصد) فقط یک رکورد فعال دارد؛ رکورد قبلی حذف می‌شود
        old = session.execute(select(Channel).where(Channel.type == channel_type)).scalars().all()
        for row in old:
            session.delete(row)
        session.flush()

        channel = Channel(
            telegram_id=telegram_id, title=title, username=username, type=channel_type
        )
        session.add(channel)
        session.flush()
        return channel

    @staticmethod
    def get_by_type(session: Session, channel_type: ChannelType) -> Channel | None:
        return session.execute(
            select(Channel).where(Channel.type == channel_type)
        ).scalar_one_or_none()
