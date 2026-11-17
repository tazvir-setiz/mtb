from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import engine, get_session
from app.database.models import (
    ForwardedMessage,
    ForwardJob,
    JobMessageResult,
    ReviewDraft,
    ReviewRequest,
    Settings as SettingsModel,
)

logger = logging.getLogger(__name__)


def cleanup_old_data(session: Session, retention_days: int = 7) -> dict[str, int]:
    """
    Safely purge operational records older than retention_days.
    Always preserves configured channels and primary settings (signature, AI keys, guard config).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    # 1. Clean Review drafts and review requests older than cutoff
    old_review_ids = [
        r[0] for r in session.query(ReviewRequest.id).filter(ReviewRequest.created_at < cutoff).all()
    ]
    deleted_drafts = 0
    deleted_reviews = 0
    if old_review_ids:
        deleted_drafts = (
            session.query(ReviewDraft)
            .filter(ReviewDraft.review_id.in_(old_review_ids))
            .delete(synchronize_session=False)
        )
        deleted_reviews = (
            session.query(ReviewRequest)
            .filter(ReviewRequest.id.in_(old_review_ids))
            .delete(synchronize_session=False)
        )

    # 2. Identify old jobs older than cutoff
    old_job_ids = [
        r[0] for r in session.query(ForwardJob.id).filter(ForwardJob.created_at < cutoff).all()
    ]

    # 3. Clean JobMessageResults for old jobs
    deleted_job_results = 0
    if old_job_ids:
        deleted_job_results = (
            session.query(JobMessageResult)
            .filter(JobMessageResult.job_id.in_(old_job_ids))
            .delete(synchronize_session=False)
        )

    # 4. Clean ForwardedMessage: either older than cutoff or referencing old_job_ids
    message_filter = ForwardedMessage.created_at < cutoff
    if old_job_ids:
        message_filter = message_filter | ForwardedMessage.job_id.in_(old_job_ids)

    deleted_messages = (
        session.query(ForwardedMessage)
        .filter(message_filter)
        .delete(synchronize_session=False)
    )

    # 5. Clean ForwardJob older than cutoff
    deleted_jobs = 0
    if old_job_ids:
        deleted_jobs = (
            session.query(ForwardJob)
            .filter(ForwardJob.id.in_(old_job_ids))
            .delete(synchronize_session=False)
        )

    # 6. Clean stale temporary settings
    deleted_temp_settings = 0
    for prefix in ("job_selection:", "review_routes:", "job_routes:", "route_sending:"):
        deleted_temp_settings += (
            session.query(SettingsModel)
            .filter(SettingsModel.key.startswith(prefix))
            .delete(synchronize_session=False)
        )

    session.flush()

    return {
        "reviews": deleted_reviews,
        "drafts": deleted_drafts,
        "job_results": deleted_job_results,
        "forwarded_messages": deleted_messages,
        "jobs": deleted_jobs,
        "temp_settings": deleted_temp_settings,
    }


def vacuum_database() -> bool:
    """
    Reclaim unused disk space on SQLite (and PostgreSQL if supported).
    """
    try:
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                conn.execution_options(isolation_level="AUTOCOMMIT").execute(text("VACUUM"))
            logger.info("SQLite VACUUM completed successfully; reclaimed unused disk space.")
            return True
        elif engine.dialect.name == "postgresql":
            # PostgreSQL autovacuum daemon handles page compaction in background
            return True
    except Exception as exc:
        logger.warning("Database VACUUM encountered a non-critical issue: %s", exc)
        return False
    return False


def run_database_cleanup(retention_days: int | None = None) -> dict[str, Any]:
    """
    Run full database cleanup and reclaim disk space.
    """
    days = retention_days if retention_days is not None else settings.db_retention_days
    logger.info("Starting database cleanup (retention=%d days)...", days)
    with get_session() as session:
        stats = cleanup_old_data(session, retention_days=days)

    vacuum_ok = vacuum_database()
    stats["vacuum"] = vacuum_ok
    logger.info("Database cleanup finished: %s", stats)
    return stats


async def auto_cleanup_loop(
    interval_hours: float | None = None,
    retention_days: int | None = None,
    initial_delay_seconds: float = 60.0,
) -> None:
    """
    Background loop that runs periodic database cleanup and disk vacuuming.
    """
    interval_sec = (
        interval_hours if interval_hours is not None else settings.db_cleanup_interval_hours
    ) * 3600
    days = retention_days if retention_days is not None else settings.db_retention_days

    logger.info(
        "Auto database cleanup task started (interval=%.1fh, retention=%dd).",
        interval_sec / 3600,
        days,
    )

    if initial_delay_seconds > 0:
        await asyncio.sleep(min(initial_delay_seconds, interval_sec))

    while True:
        try:
            run_database_cleanup(retention_days=days)
        except asyncio.CancelledError:
            logger.info("Auto database cleanup loop cancelled.")
            raise
        except Exception as exc:
            logger.error("Auto database cleanup loop encountered an error: %s", exc, exc_info=True)

        await asyncio.sleep(interval_sec)
