from __future__ import annotations

import json
import logging

from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import (
    ChannelRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.services.progress_service import ProgressReporter
from app.telegram.client import ensure_started
from app.telegram.forward_service import forward_range, request_stop, retry_failed
from app.ui import keyboards, messages

logger = logging.getLogger(__name__)


def configured_channels():
    with get_session() as session:
        return (
            ChannelRepository.get_all_by_type(session, ChannelType.SOURCE),
            ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION),
        )


def get_channels(selection=None):
    sources, destinations = configured_channels()
    selection = selection or {}
    selected_source = selection.get("transfer_source")
    selected_destinations = selection.get("transfer_destinations")
    source = next((c for c in sources if c.telegram_id == selected_source), None)
    if selected_source is None and len(sources) == 1:
        source = sources[0]
    if selected_destinations is None and len(destinations) == 1:
        selected_destinations = [destinations[0].telegram_id]
    chosen = [c for c in destinations if c.telegram_id in (selected_destinations or [])]
    if set(selected_destinations or []) != {c.telegram_id for c in chosen}:
        chosen = []  # Configuration changed after selection: require selection again.
    return (
        source.telegram_id if source else None,
        [c.telegram_id for c in chosen],
        source.title if source else "مبدأ را انتخاب کنید",
        (
            "، ".join(c.title for c in chosen)
            if len(chosen) <= 3
            else f"{len(chosen)} مقصد انتخاب‌شده"
        )
        or "مقصدها را انتخاب کنید",
    )


def create_job(source_id: int, dest_id: int | list[int], start_id: int, end_id: int) -> int:
    return create_job_for_ids(source_id, dest_id, list(range(start_id, end_id + 1)))


def create_job_for_ids(source_id: int, dest_id: int | list[int], ids: list[int]) -> int:
    destinations = list(dict.fromkeys(dest_id if isinstance(dest_id, list) else [dest_id]))
    ids = sorted(set(ids))
    if not destinations or not ids:
        raise ValueError("Select at least one message and destination")
    with get_session() as session:
        jobs = [
            ForwardJobRepository.create(
                session, source_id, destination, min(ids), max(ids), total_messages=len(ids)
            )
            for destination in destinations
        ]
        for job in jobs:
            SettingsRepository.set(session, f"job_selection:{job.id}", json.dumps(ids))
        SettingsRepository.set(
            session, f"job_routes:{jobs[0].id}", json.dumps([j.id for j in jobs])
        )
        return jobs[0].id


def remaining_ids(session, job):
    raw = SettingsRepository.get(session, f"job_selection:{job.id}")
    if raw is not None:
        ids = json.loads(raw)
    elif job.total_messages == job.end_message_id - job.start_message_id + 1:
        ids = range(job.start_message_id, job.end_message_id + 1)
    else:
        raise ValueError("فهرست انتخاب این انتقال قدیمی ذخیره نشده؛ شناسه‌ها را دوباره انتخاب کنید.")
    from app.services.transfer_routes import job_routes

    cursors = [
        ForwardJobRepository.get(session, route_job).last_processed_message_id or 0
        for _, route_job in job_routes(session, job)
    ]
    return [value for value in ids if value > min(cursors)]


async def run_transfer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    progress_message_id: int,
    job_id: int,
    source_id: int,
    dest_id: int | list[int],
    message_ids: list[int],
) -> None:
    client = await ensure_started()
    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)
    await forward_range(
        client, job_id, source_id, dest_id, message_ids, on_progress=reporter.update
    )

    await show_result(context, chat_id, progress_message_id, job_id)


async def show_result(context, chat_id, progress_message_id, job_id):
    with get_session() as session:
        from app.database.models import JobStatus

        job = ForwardJobRepository.get(session, job_id)
        if job is None:
            return
        finished = job.status == JobStatus.COMPLETED
        from app.services.transfer_routes import job_routes

        jobs = [
            ForwardJobRepository.get(session, route_job)
            for _, route_job in job_routes(session, job)
        ]
        total = sum(j.total_messages for j in jobs)
        success = sum(j.successful_messages for j in jobs)
        skipped = sum(j.skipped_messages for j in jobs)
        failed = sum(j.failed_messages for j in jobs)
        started = job.started_at
        finished_at = job.finished_at

    if finished:
        elapsed = int((finished_at - started).total_seconds()) if started and finished_at else 0
        text = messages.final_result_text(total, success, skipped, failed, elapsed)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_message_id,
            text=text,
            reply_markup=keyboards.result_menu(has_errors=failed > 0),
        )


def stop_job(job_id: int) -> None:
    request_stop(job_id)


async def run_retry(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, progress_message_id: int, job_id: int
) -> None:
    client = await ensure_started()
    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)
    await retry_failed(client, job_id, on_progress=reporter.update)
    await show_result(context, chat_id, progress_message_id, job_id)


def get_failed_items(job_id: int) -> list[tuple[int, str]]:
    with get_session() as session:
        from app.services.transfer_routes import job_routes

        job = ForwardJobRepository.get(session, job_id)
        if job is None:
            return []
        from sqlalchemy import select

        from app.database.models import ForwardedMessage
        from app.services.transfer_routes import failed_ids

        items = []
        for destination, route_job in job_routes(session, job):
            for message_id in sorted(failed_ids(session, route_job)):
                record = session.scalar(
                    select(ForwardedMessage).where(
                        ForwardedMessage.source_channel_id == job.source_channel_id,
                        ForwardedMessage.source_message_id == message_id,
                        ForwardedMessage.destination_channel_id == destination,
                    )
                )
                error = record.error if record and record.error else "نیازمند تلاش مجدد"
                items.append((message_id, f"{destination}: {error}"))
        return items
