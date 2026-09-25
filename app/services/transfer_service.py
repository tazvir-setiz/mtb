from __future__ import annotations

import logging

from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
)
from app.services.progress_service import ProgressReporter
from app.telegram.client import ensure_started
from app.telegram.forward_service import forward_range, request_stop, retry_failed
from app.ui import keyboards, messages

logger = logging.getLogger(__name__)


def get_channels() -> tuple[int | None, int | None, str, str]:
    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)
    source_id = source.telegram_id if source else None
    dest_id = destination.telegram_id if destination else None
    source_title = source.title if source else "❌ تنظیم نشده"
    dest_title = destination.title if destination else "❌ تنظیم نشده"
    return source_id, dest_id, source_title, dest_title


def create_job(source_id: int, dest_id: int, start_id: int, end_id: int) -> int:
    with get_session() as session:
        job = ForwardJobRepository.create(
            session, source_id, dest_id, start_id, end_id, total_messages=end_id - start_id + 1
        )
        return job.id


def create_job_for_ids(source_id: int, dest_id: int, ids: list[int]) -> int:
    with get_session() as session:
        job = ForwardJobRepository.create(
            session, source_id, dest_id, min(ids), max(ids), total_messages=len(ids)
        )
        return job.id


async def run_transfer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    progress_message_id: int,
    job_id: int,
    source_id: int,
    dest_id: int,
    message_ids: list[int],
) -> None:
    client = await ensure_started()
    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)
    await forward_range(
        client, job_id, source_id, dest_id, message_ids, on_progress=reporter.update
    )

    with get_session() as session:
        from app.database.models import JobStatus

        job = ForwardJobRepository.get(session, job_id)
        if job is None:
            return
        finished = job.status == JobStatus.COMPLETED
        total = job.total_messages
        success = job.successful_messages
        skipped = job.skipped_messages
        failed = job.failed_messages
        started = job.started_at
        finished_at = job.finished_at

    if finished:
        elapsed = int((finished_at - started).total_seconds()) if started and finished_at else 0
        text = messages.final_result_text(total, success, skipped, failed, elapsed)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message_id,
            text=text,
            reply_markup=keyboards.result_menu(),
        )


def stop_job(job_id: int) -> None:
    request_stop(job_id)


async def run_retry(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, progress_message_id: int, job_id: int
) -> None:
    client = await ensure_started()
    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)
    await retry_failed(client, job_id, on_progress=reporter.update)


def get_failed_items(job_id: int) -> list[tuple[int, str]]:
    with get_session() as session:
        records = ForwardedMessageRepository.failed_for_job(session, job_id)
    return [(r.source_message_id, r.error or "خطای نامشخص") for r in records]
