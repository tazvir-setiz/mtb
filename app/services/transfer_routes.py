"""Persist a manual fan-out as ordinary per-route jobs, preserving legacy jobs."""

import json

from sqlalchemy import select

from app.database.models import JobMessageResult, MessageStatus
from app.database.repository import (
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)


def job_routes(session, job):
    raw = SettingsRepository.get(session, f"job_routes:{job.id}")
    if raw is None:
        return [(job.destination_channel_id, job.id)]
    ids = json.loads(raw)
    if not isinstance(ids, list) or not ids:
        raise ValueError("Invalid persisted transfer routes")
    jobs = [ForwardJobRepository.get(session, value) for value in ids]
    if any(item is None or item.source_channel_id != job.source_channel_id for item in jobs):
        raise ValueError("Transfer route job is missing or has a different source")
    return [(item.destination_channel_id, item.id) for item in jobs]


def failed_ids(session, job_id):
    # A competing transfer may own the canonical route record now. Keep the
    # original job retryable using its ledger, with a fallback for legacy jobs.
    ids = set(
        session.scalars(
            select(JobMessageResult.message_id).where(
                JobMessageResult.job_id == job_id, JobMessageResult.status == MessageStatus.FAILED
            )
        )
    )
    ids.update(
        row.source_message_id for row in ForwardedMessageRepository.failed_for_job(session, job_id)
    )
    return ids
