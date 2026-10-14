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
    selected_sources = selection.get("transfer_sources")
    selected_source = selection.get("transfer_source")
    if selected_sources is None:
        if selected_source is not None:
            selected_sources = [selected_source]
        elif len(sources) == 1:
            selected_sources = [sources[0].telegram_id]
        else:
            selected_sources = []

    selected_destinations = selection.get("transfer_destinations")
    if selected_destinations is None and len(destinations) == 1:
        selected_destinations = [destinations[0].telegram_id]

    chosen_sources = [c for c in sources if c.telegram_id in (selected_sources or [])]
    if set(selected_sources or []) != {c.telegram_id for c in chosen_sources}:
        chosen_sources = []

    chosen_destinations = [c for c in destinations if c.telegram_id in (selected_destinations or [])]
    if set(selected_destinations or []) != {c.telegram_id for c in chosen_destinations}:
        chosen_destinations = []

    if len(chosen_sources) == 1:
        source_val = chosen_sources[0].telegram_id
        source_title = chosen_sources[0].title
    elif len(chosen_sources) > 1:
        source_val = [c.telegram_id for c in chosen_sources]
        source_title = (
            "، ".join(c.title for c in chosen_sources)
            if len(chosen_sources) <= 3
            else f"{len(chosen_sources)} مبدأ انتخاب‌شده"
        )
    else:
        source_val = None
        source_title = "مبدأ را انتخاب کنید"

    dest_title = (
        "، ".join(c.title for c in chosen_destinations)
        if len(chosen_destinations) <= 3
        else f"{len(chosen_destinations)} مقصد انتخاب‌شده"
    ) or "مقصدها را انتخاب کنید"

    return (
        source_val,
        [c.telegram_id for c in chosen_destinations],
        source_title,
        dest_title,
    )


def create_job(source_id: int | list[int], dest_id: int | list[int], start_id: int, end_id: int) -> int:
    return create_job_for_ids(source_id, dest_id, list(range(start_id, end_id + 1)))


def create_job_for_ids(source_id: int | list[int], dest_id: int | list[int], ids: list[int]) -> int:
    sources = source_id if isinstance(source_id, list) else [source_id]
    destinations = list(dict.fromkeys(dest_id if isinstance(dest_id, list) else [dest_id]))
    ids = sorted(set(ids))
    if not sources or not destinations or not ids:
        raise ValueError("Select at least one message and destination")
    with get_session() as session:
        batch_primary_job_ids = []
        for src_id in sources:
            jobs = [
                ForwardJobRepository.create(
                    session, src_id, destination, min(ids), max(ids), total_messages=len(ids)
                )
                for destination in destinations
            ]
            for job in jobs:
                SettingsRepository.set(session, f"job_selection:{job.id}", json.dumps(ids))
            SettingsRepository.set(
                session, f"job_routes:{jobs[0].id}", json.dumps([j.id for j in jobs])
            )
            batch_primary_job_ids.append(jobs[0].id)
        if len(batch_primary_job_ids) > 1:
            for p_id in batch_primary_job_ids:
                SettingsRepository.set(
                    session, f"job_batch:{p_id}", json.dumps(batch_primary_job_ids)
                )
        return batch_primary_job_ids[0]


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
    source_id: int | list[int],
    dest_id: int | list[int],
    message_ids: list[int],
) -> None:
    from app.database.models import JobStatus

    client = await ensure_started()
    with get_session() as session:
        raw_batch = SettingsRepository.get(session, f"job_batch:{job_id}")
        job_ids = json.loads(raw_batch) if raw_batch else [job_id]
        jobs_data = []
        for j_id in job_ids:
            j = ForwardJobRepository.get(session, j_id)
            if j:
                jobs_data.append((j_id, j.source_channel_id, j.status))

    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)

    dest_count = len(dest_id) if isinstance(dest_id, list) else 1
    overall_total = len(jobs_data) * dest_count * len(message_ids)

    accumulated_processed = 0
    accumulated_success = 0
    accumulated_skipped = 0
    accumulated_failed = 0

    with get_session() as session:
        from app.services.transfer_routes import job_routes

        for j_id, _, status in jobs_data:
            if status == JobStatus.COMPLETED:
                j = ForwardJobRepository.get(session, j_id)
                if j:
                    for _, route_job in job_routes(session, j):
                        rj = ForwardJobRepository.get(session, route_job)
                        if rj:
                            accumulated_processed += (
                                rj.successful_messages + rj.skipped_messages + rj.failed_messages
                            )
                            accumulated_success += rj.successful_messages
                            accumulated_skipped += rj.skipped_messages
                            accumulated_failed += rj.failed_messages

    stopped = False
    for j_id, src_id, _ in jobs_data:
        with get_session() as session:
            j = ForwardJobRepository.get(session, j_id)
            if j is None or j.status == JobStatus.COMPLETED:
                continue
            if j.status == JobStatus.PAUSED:
                remaining = remaining_ids(session, j)
            else:
                remaining = message_ids

        cur_processed = cur_success = cur_skipped = cur_failed = 0

        async def combined_progress(snap: ProgressSnapshot):
            nonlocal cur_processed, cur_success, cur_skipped, cur_failed
            cur_processed = snap.processed
            cur_success = snap.success
            cur_skipped = snap.skipped
            cur_failed = snap.failed
            combined_snap = ProgressSnapshot(
                job_id,
                overall_total,
                accumulated_processed + snap.processed,
                accumulated_success + snap.success,
                accumulated_skipped + snap.skipped,
                accumulated_failed + snap.failed,
                snap.stopped,
            )
            await reporter.update(combined_snap)

        target_dest = dest_id if isinstance(dest_id, int) else dest_id[0]
        await forward_range(
            client,
            j_id,
            src_id,
            target_dest,
            remaining,
            on_progress=combined_progress,
        )

        with get_session() as session:
            j = ForwardJobRepository.get(session, j_id)
            if j and j.status == JobStatus.PAUSED:
                stopped = True
                break

        accumulated_processed += cur_processed
        accumulated_success += cur_success
        accumulated_skipped += cur_skipped
        accumulated_failed += cur_failed

    if not stopped:
        await show_result(context, chat_id, progress_message_id, job_id)


async def show_result(context, chat_id, progress_message_id, job_id):
    with get_session() as session:
        from app.database.models import JobStatus

        raw_batch = SettingsRepository.get(session, f"job_batch:{job_id}")
        job_ids = json.loads(raw_batch) if raw_batch else [job_id]

        primary_job = ForwardJobRepository.get(session, job_id)
        if primary_job is None:
            return

        from app.services.transfer_routes import job_routes

        all_jobs = []
        for j_id in job_ids:
            cur_job = ForwardJobRepository.get(session, j_id)
            if cur_job:
                for _, route_job in job_routes(session, cur_job):
                    rj = ForwardJobRepository.get(session, route_job)
                    if rj:
                        all_jobs.append(rj)

        finished = all(j.status == JobStatus.COMPLETED for j in all_jobs) if all_jobs else False
        total = sum(j.total_messages for j in all_jobs)
        success = sum(j.successful_messages for j in all_jobs)
        skipped = sum(j.skipped_messages for j in all_jobs)
        failed = sum(j.failed_messages for j in all_jobs)
        started = primary_job.started_at
        finished_candidates = [j.finished_at for j in all_jobs if j.finished_at]
        finished_at = max(finished_candidates) if finished_candidates else primary_job.finished_at

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
    with get_session() as session:
        raw_batch = SettingsRepository.get(session, f"job_batch:{job_id}")
        job_ids = json.loads(raw_batch) if raw_batch else [job_id]
    for j_id in job_ids:
        request_stop(j_id)


async def run_retry(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, progress_message_id: int, job_id: int
) -> None:
    client = await ensure_started()
    with get_session() as session:
        raw_batch = SettingsRepository.get(session, f"job_batch:{job_id}")
        job_ids = json.loads(raw_batch) if raw_batch else [job_id]

    reporter = ProgressReporter(context.bot, chat_id, progress_message_id)
    for j_id in job_ids:
        await retry_failed(client, j_id, on_progress=reporter.update)
    await show_result(context, chat_id, progress_message_id, job_id)


def get_failed_items(job_id: int) -> list[tuple[int, str]]:
    with get_session() as session:
        from app.services.transfer_routes import job_routes

        raw_batch = SettingsRepository.get(session, f"job_batch:{job_id}")
        job_ids = json.loads(raw_batch) if raw_batch else [job_id]

        from sqlalchemy import select
        from app.database.models import ForwardedMessage
        from app.services.transfer_routes import failed_ids

        items = []
        for j_id in job_ids:
            job = ForwardJobRepository.get(session, j_id)
            if job is None:
                continue
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
