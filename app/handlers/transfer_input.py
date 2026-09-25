from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.states import KEY_RANGE_START, State, get_state, set_state
from app.services import transfer_service
from app.ui import keyboards, messages
from app.utils.validators import parse_id_list, validate_message_id, validate_range


async def start_range_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_transfer_input(context.user_data)
    set_state(context.user_data, State.RANGE_INPUT_START)
    await update.callback_query.message.reply_text(
        messages.ask_start_id(), reply_markup=keyboards.cancel_only(force_reply=True)
    )


async def start_ids_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_transfer_input(context.user_data)
    set_state(context.user_data, State.IDS_INPUT)
    await update.callback_query.message.reply_text(
        "📋 Message IDهای مورد نظر را با کاما یا در خطوط جدا ارسال کنید.\n\nمثال:\n101,102,105",
        reply_markup=keyboards.cancel_only(force_reply=True),
    )


async def handle_text_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, state: State
) -> None:
    handlers = {
        State.RANGE_INPUT_START: read_range_start,
        State.RANGE_INPUT_END: read_range_end,
        State.IDS_INPUT: read_message_ids,
    }
    handler = handlers.get(state)
    if handler:
        await handler(update, context)


async def read_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    value, error = validate_message_id(text)
    if error:
        await update.message.reply_text(f"⚠️ {error}", reply_markup=keyboards.cancel_only())
        return
    context.user_data[KEY_RANGE_START] = value
    set_state(context.user_data, State.RANGE_INPUT_END)
    await update.message.reply_text(
        messages.ask_end_id(), reply_markup=keyboards.cancel_only(force_reply=True)
    )


async def read_range_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
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


async def read_message_ids(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
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


async def show_confirm_from_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_id = context.user_data.get(KEY_RANGE_START)
    end_id = context.user_data.get("range_end")
    if start_id is None or end_id is None or get_state(context.user_data) != State.CONFIRM_TRANSFER:
        await update.callback_query.message.reply_text(
            "این انتخاب منقضی شده؛ از /menu دوباره شروع کنید."
        )
        return
    _, _, source_title, dest_title = transfer_service.get_channels()
    count = end_id - start_id + 1
    set_state(context.user_data, State.CONFIRM_TRANSFER)
    await update.callback_query.edit_message_text(
        messages.confirm_transfer_text(count, source_title, dest_title),
        reply_markup=keyboards.confirm_transfer(),
    )


async def edit_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_range_flow(update, context)


def clear_transfer_input(user_data: dict) -> None:
    for key in ("explicit_ids", KEY_RANGE_START, "range_end"):
        user_data.pop(key, None)
