from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.states import (
    KEY_CURRENT_JOB_ID,
    KEY_PROGRESS_MESSAGE_ID,
    KEY_RANGE_START,
    State,
    get_state,
    set_state,
)
from app.handlers.transfer_controls import pause_transfer as pause_transfer
from app.handlers.transfer_controls import resume_transfer as resume_transfer
from app.handlers.transfer_controls import retry_failed_messages as retry_failed_messages
from app.handlers.transfer_controls import show_errors as show_errors
from app.handlers.transfer_input import edit_range as edit_range
from app.handlers.transfer_input import handle_text_input as handle_text_input
from app.handlers.transfer_input import show_confirm_from_range as show_confirm_from_range
from app.handlers.transfer_input import start_ids_flow as start_ids_flow
from app.handlers.transfer_input import start_range_flow as start_range_flow
from app.services import transfer_service
from app.ui import keyboards, messages
from app.ui.buttons.transfer import destination_selection, source_selection


async def show_transfer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.handlers.transfer_input import clear_transfer_input

    clear_transfer_input(context.user_data)
    context.user_data.pop("transfer_source", None)
    context.user_data.pop("transfer_sources", None)
    context.user_data.pop("transfer_source_page", None)
    context.user_data.pop("transfer_destination_page", None)
    context.user_data.pop("transfer_destinations", None)
    sources, destinations = transfer_service.configured_channels()
    if not sources or not destinations:
        await update.callback_query.answer(
            "ابتدا کانال مبدأ و مقصد را تنظیم کنید.", show_alert=True
        )
        return
    set_state(context.user_data, State.TRANSFER_MENU)
    if len(sources) == 1:
        context.user_data["transfer_source"] = sources[0].telegram_id
        context.user_data["transfer_sources"] = [sources[0].telegram_id]
        await show_destinations(update, context)
        return
    await show_sources(update, context)


async def show_sources(update, context):
    from app.ui.callbacks import parse

    if get_state(context.user_data) != State.TRANSFER_MENU:
        return
    sources, _ = transfer_service.configured_channels()
    _, action, arg = parse(getattr(update.callback_query, "data", "") or "")
    page = int(arg) if action == "sources" and arg and arg.isdigit() else 0
    page = min(page, max(0, (len(sources) - 1) // 10))
    context.user_data["transfer_source_page"] = page
    chosen = context.user_data.setdefault("transfer_sources", [])
    await update.callback_query.edit_message_text(
        "📥 یک یا چند کانال مبدأ را برای انتقال انتخاب کنید:",
        reply_markup=source_selection(sources, chosen, page),
    )


async def select_source(update, context):
    from app.ui.callbacks import parse

    if get_state(context.user_data) != State.TRANSFER_MENU:
        return
    _, _, arg = parse(update.callback_query.data)
    sources, _ = transfer_service.configured_channels()
    if arg == "all":
        context.user_data["transfer_sources"] = [c.telegram_id for c in sources]
        if len(sources) == 1:
            context.user_data["transfer_source"] = sources[0].telegram_id
        else:
            context.user_data.pop("transfer_source", None)
        await show_destinations(update, context)
        return

    source = next((c for c in sources if str(c.telegram_id) == arg), None)
    if source is None:
        await show_transfer_menu(update, context)
        return

    chosen = context.user_data.setdefault("transfer_sources", [])
    if source.telegram_id in chosen:
        chosen.remove(source.telegram_id)
    else:
        chosen.append(source.telegram_id)

    if len(chosen) == 1:
        context.user_data["transfer_source"] = chosen[0]
    else:
        context.user_data.pop("transfer_source", None)

    page = context.user_data.get("transfer_source_page", 0)
    await update.callback_query.edit_message_text(
        "📥 یک یا چند کانال مبدأ را برای انتقال انتخاب کنید:",
        reply_markup=source_selection(sources, chosen, page),
    )


async def show_destinations(update, context):
    from app.ui.callbacks import parse

    if get_state(context.user_data) != State.TRANSFER_MENU:
        return
    chosen_sources = context.user_data.get("transfer_sources")
    if not chosen_sources and "transfer_source" in context.user_data:
        chosen_sources = [context.user_data["transfer_source"]]
        context.user_data["transfer_sources"] = chosen_sources
    if not chosen_sources:
        await update.callback_query.answer("حداقل یک مبدأ انتخاب کنید.", show_alert=True)
        return
    _, destinations = transfer_service.configured_channels()
    _, action, arg = parse(getattr(update.callback_query, "data", "") or "")
    page = context.user_data.get("transfer_destination_page", 0)
    if action == "destinations" and arg and arg.isdigit():
        page = int(arg)
    page = min(page, max(0, (len(destinations) - 1) // 10))
    context.user_data["transfer_destination_page"] = page
    chosen = context.user_data.setdefault("transfer_destinations", [])
    if len(destinations) == 1:
        chosen[:] = [destinations[0].telegram_id]
    await update.callback_query.edit_message_text(
        "📤 یک یا چند مقصد را انتخاب کنید.",
        reply_markup=destination_selection(destinations, chosen, page),
    )


async def toggle_destination(update, context):
    from app.ui.callbacks import parse

    if get_state(context.user_data) != State.TRANSFER_MENU:
        return
    _, _, arg = parse(update.callback_query.data)
    _, destinations = transfer_service.configured_channels()
    channel = next((c for c in destinations if str(c.telegram_id) == arg), None)
    if channel is None:
        await show_transfer_menu(update, context)
        return
    chosen = context.user_data.setdefault("transfer_destinations", [])
    if channel.telegram_id in chosen:
        chosen.remove(channel.telegram_id)
    else:
        chosen.append(channel.telegram_id)
    await show_destinations(update, context)


async def confirm_routes(update, context):
    if get_state(context.user_data) != State.TRANSFER_MENU:
        return
    source_id, destinations, source_title, dest_title = transfer_service.get_channels(
        context.user_data
    )
    if source_id is None or not destinations:
        await update.callback_query.answer("یک مبدأ و حداقل یک مقصد انتخاب کنید.", show_alert=True)
        return
    await update.callback_query.edit_message_text(
        messages.transfer_menu_text(source_title, dest_title),
        reply_markup=keyboards.transfer_menu(),
    )


async def start_new_messages_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.handlers.dashboard import show_auto_forward

    await show_auto_forward(update, context)


async def confirm_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if get_state(context.user_data) != State.CONFIRM_TRANSFER:
        await update.callback_query.message.reply_text(
            "این درخواست قبلاً اجرا شده یا منقضی شده است. /menu"
        )
        return
    source_id, dest_id, source_title, dest_title = transfer_service.get_channels(context.user_data)
    start_id = context.user_data.get(KEY_RANGE_START)
    end_id = context.user_data.get("range_end")
    explicit_ids = context.user_data.get("explicit_ids")
    if (
        source_id is None
        or not dest_id
        or (not explicit_ids and (start_id is None or end_id is None))
    ):
        await update.callback_query.message.reply_text(
            "اطلاعات انتقال کامل نیست. از /menu دوباره شروع کنید."
        )
        return

    if explicit_ids:
        message_ids = explicit_ids
        job_id = transfer_service.create_job_for_ids(source_id, dest_id, message_ids)
    else:
        message_ids = list(range(start_id, end_id + 1))
        job_id = transfer_service.create_job(source_id, dest_id, start_id, end_id)

    context.user_data[KEY_CURRENT_JOB_ID] = job_id
    set_state(context.user_data, State.TRANSFERRING)

    sources = source_id if isinstance(source_id, list) else [source_id]
    total_deliveries = len(message_ids) * len(dest_id) * len(sources)

    await update.callback_query.edit_message_text(
        messages.progress_text(0, total_deliveries, 0, 0, 0, 0),
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
