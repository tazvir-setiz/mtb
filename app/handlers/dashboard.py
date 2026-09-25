from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import ChannelRepository, ForwardedMessageRepository
from app.handlers.states import State, reset, set_state
from app.ui import keyboards, messages


def _dashboard_content() -> tuple[str, object]:
    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)
        stats = ForwardedMessageRepository.stats(session)

    text = messages.dashboard(
        source.title if source else None,
        destination.title if destination else None,
        stats["success"],
    )
    markup = keyboards.main_menu(source is not None, destination is not None)
    return text, markup


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False) -> None:
    reset(context.user_data)
    text, markup = _dashboard_content()
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)
    set_state(context.user_data, State.MAIN_MENU)
