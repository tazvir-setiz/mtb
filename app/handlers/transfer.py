from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.states import (
    KEY_CURRENT_JOB_ID,
    KEY_PROGRESS_MESSAGE_ID,
    KEY_RANGE_START,
    State,
    set_state,
)
from app.services import transfer_service
from app.ui import keyboards, messages
from app.utils.validators import validate_message_id, validate_range

logger = logging.getLogger(__name__)


async def show_transfer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_id, dest_id, source_title, dest_title = transfer_service.get_channels()
    if source_id is None or dest_id is None:
        await update.callback_query.answer(
            "ابتدا کانال مبدأ و مقصد را تنظیم کنید.", show_alert=True
        )
        return
    set_state(context.user_data, State.TRANSFER_MENU)
    await update.callback_query.edit_message_text(
        messages.transfer_menu_text(source_title, dest_title),
        reply_markup=keyboards.transfer_menu(),
    )


async def start_range_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(context.user_data, State.RANGE_INPUT_START)
    await update.callback_query.edit_message_text(
        messages.ask_start_id(), reply_markup=keyboards.cancel_only()
    )


async def start_ids_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    set_state(context.user_data, State.IDS_INPUT)
    await update.callback_query.edit_message_text(
        "📋 Message IDهای مورد نظر را با کاما یا در خطوط جدا ارسال کنید.\n\nمثال:\n101,102,105",
        reply_markup=keyboards.cancel_only(),
    )


async def start_new_messages_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer(
        "این قابلیت نیازمند دریافت آنی پیام‌های جدید کانال مبدأ است و به‌زودی فعال می‌شود.",
        show_alert=True,
    )


async def handle_text_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, state: State
) -> None:
    text = update.message.text.strip()

    if state == State.RANGE_INPUT_START:
        value, error = validate_message_id(text)
        if error:
            await update.message.reply_text(f"⚠️ {error}", reply_markup=keyboards.cancel_only())
            return
        context.user_data[KEY_RANGE_START] = value
        set_state(context.user_data, State.RANGE_INPUT_END)
        await update.message.reply_text(messages.ask_end_id(), reply_markup=keyboards.cancel_only())
        return

    if state == State.RANGE_INPUT_END:
        start_id = context.user_data.get(KEY_RANGE_START)
        value, error = validate_message_id(text)
        if not error:
            error = validate_range(start_id, value)
        if error:
            await update.message.reply_text(f"⚠️ {error}", reply_markup=keyboards.cancel_only())
            return
        _, _, source_title, dest_title = transfer_service.get_channels()
        context.user_data["range_end"] = value
        set_state(context.user_data, State.CONFIRM_TRANSFER)
        await update.message.reply_text(
            messages.range_summary_text(source_title, dest_title, start_id, value),
            reply_markup=keyboards.range_summary(),
        )
        return

    if state == State.IDS_INPUT:
        from app.utils.validators import parse_id_list

        ids, error = parse_id_list(text)
        if error:
            await update.message.reply_text(f"⚠️ {error}", reply_markup=keyboards.cancel_only())
            return
        context.user_data["explicit_ids"] = ids
        _, _, source_title, dest_title = transfer_service.get_channels()
        set_state(context.user_data, State.CONFIRM_TRANSFER)
        await update.message.reply_text(
            messages.confirm_transfer_text(len(ids), source_title, dest_title),
            reply_markup=keyboards.confirm_transfer(),
        )
        return


async def show_confirm_from_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_id = context.user_data.get(KEY_RANGE_START)
    end_id = context.user_data.get("range_end")
    _, _, source_title, dest_title = transfer_service.get_channels()
    count = end_id - start_id + 1
    set_state(context.user_data, State.CONFIRM_TRANSFER)
    await update.callback_query.edit_message_text(
        messages.confirm_transfer_text(count, source_title, dest_title),
        reply_markup=keyboards.confirm_transfer(),
    )


async def edit_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_range_flow(update, context)


async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_id, dest_id, source_title, dest_title = transfer_service.get_channels()
    start_id = context.user_data.get(KEY_RANGE_START)
    end_id = context.user_data.get("range_end")
    explicit_ids = context.user_data.get("explicit_ids")

    if explicit_ids:
        message_ids = explicit_ids
        job_id = transfer_service.create_job_for_ids(source_id, dest_id, message_ids)
    else:
        message_ids = list(range(start_id, end_id + 1))
        job_id = transfer_service.create_job(source_id, dest_id, start_id, end_id)

    context.user_data[KEY_CURRENT_JOB_ID] = job_id
    set_state(context.user_data, State.TRANSFERRING)

    await update.callback_query.edit_message_text(
        messages.progress_text(0, len(message_ids), 0, 0, 0, 0),
        reply_markup=keyboards.in_progress(),
    )
    progress_message_id = update.callback_query.message.message_id
    context.user_data[KEY_PROGRESS_MESSAGE_ID] = progress_message_id
    chat_id = update.effective_chat.id

    asyncio.create_task(
        transfer_service.run_transfer(
            context, chat_id, progress_message_id, job_id, source_id, dest_id, message_ids
        )
    )


async def pause_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    job_id = context.user_data.get(KEY_CURRENT_JOB_ID)
    if job_id:
        transfer_service.stop_job(job_id)
    await update.callback_query.answer("در حال توقف عملیات...")


async def resume_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    job_id = context.user_data.get(KEY_CURRENT_JOB_ID)
    if not job_id:
        await update.callback_query.answer("عملیات فعالی یافت نشد.", show_alert=True)
        return
    from app.database.database import get_session
    from app.database.repository import ForwardJobRepository

    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        remaining = list(
            range(
                job.last_processed_message_id + 1
                if job.last_processed_message_id
                else job.start_message_id,
                job.end_message_id + 1,
            )
        )
        source_id, dest_id = job.source_channel_id, job.destination_channel_id

    set_state(context.user_data, State.TRANSFERRING)
    progress_message_id = update.callback_query.message.message_id
    context.user_data[KEY_PROGRESS_MESSAGE_ID] = progress_message_id
    chat_id = update.effective_chat.id
    asyncio.create_task(
        transfer_service.run_transfer(
            context, chat_id, progress_message_id, job_id, source_id, dest_id, remaining
        )
    )


async def show_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    job_id = context.user_data.get(KEY_CURRENT_JOB_ID)
    items = transfer_service.get_failed_items(job_id) if job_id else []
    await update.callback_query.edit_message_text(
        messages.failed_messages_text(items), reply_markup=keyboards.failed_messages_menu()
    )


async def retry_failed_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    job_id = context.user_data.get(KEY_CURRENT_JOB_ID)
    if not job_id:
        await update.callback_query.answer("عملیات فعالی یافت نشد.", show_alert=True)
        return
    set_state(context.user_data, State.TRANSFERRING)
    progress_message_id = update.callback_query.message.message_id
    context.user_data[KEY_PROGRESS_MESSAGE_ID] = progress_message_id
    chat_id = update.effective_chat.id
    await update.callback_query.edit_message_text(
        "🔄 در حال تلاش مجدد برای پیام‌های ناموفق...", reply_markup=keyboards.in_progress()
    )
    asyncio.create_task(transfer_service.run_retry(context, chat_id, progress_message_id, job_id))
