from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    ForwardedMessage,
    ForwardJob,
    JobMessageResult,
    ReviewDraft,
    ReviewRequest,
)
from app.database.models import Settings as SettingsModel


class SettingsRepository:
    @staticmethod
    def get(session: Session, key: str, default: str | None = None) -> str | None:
        row = session.execute(
            select(SettingsModel).where(SettingsModel.key == key)
        ).scalar_one_or_none()
        return row.value if row else default

    @staticmethod
    def set(session: Session, key: str, value: str) -> None:
        row = session.execute(
            select(SettingsModel).where(SettingsModel.key == key)
        ).scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(SettingsModel(key=key, value=value))
        session.flush()

    @staticmethod
    def clear_all_data(session: Session) -> None:
        session.query(ReviewDraft).delete()
        session.query(ReviewRequest).delete()
        for prefix in ("review_routes:", "job_routes:", "route_sending:"):
            session.query(SettingsModel).filter(SettingsModel.key.startswith(prefix)).delete()
        session.query(JobMessageResult).delete()
        session.query(SettingsModel).filter(SettingsModel.key.startswith("job_selection:")).delete()
        session.query(ForwardedMessage).delete()
        session.query(ForwardJob).delete()
        session.flush()
