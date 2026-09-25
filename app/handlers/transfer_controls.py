import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.repository import ForwardJobRepository
from app.handlers.states import KEY_CURRENT_JOB_ID, KEY_PROGRESS_MESSAGE_ID, State, set_state
from app.services import transfer_service
from app.ui import keyboards, messages


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
