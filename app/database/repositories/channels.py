from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Channel, ChannelType


class ChannelRepository:
    @staticmethod
    def remove(session: Session, channel_type: ChannelType, telegram_id: int) -> bool:
        from sqlalchemy import delete

        return bool(
            session.execute(
                delete(Channel).where(
                    Channel.type == channel_type, Channel.telegram_id == telegram_id
                )
            ).rowcount
        )

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

        channel = Channel(
            telegram_id=telegram_id, title=title, username=username, type=channel_type
        )
        session.add(channel)
        session.flush()
        return channel

    @staticmethod
    def get_by_type(session: Session, channel_type: ChannelType) -> Channel | None:
        return (
            session.execute(
                select(Channel)
                .where(Channel.type == channel_type)
                .order_by(Channel.updated_at.desc(), Channel.id.desc())
            )
            .scalars()
            .first()
        )

    @staticmethod
    def get_all_by_type(session: Session, channel_type: ChannelType) -> list[Channel]:
        return (
            session.execute(
                select(Channel)
                .where(Channel.type == channel_type)
                .order_by(Channel.created_at.asc(), Channel.id.asc())
            )
            .scalars()
            .all()
        )
