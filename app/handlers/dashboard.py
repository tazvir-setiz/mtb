from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import ChannelRepository, ForwardedMessageRepository
from app.handlers.states import State, reset, set_state
from app.telegram import auto_forward
from app.telegram.client import ensure_started
from app.ui import keyboards, messages


def _dashboard_content() -> tuple[str, object]:
    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)
        stats = ForwardedMessageRepository.stats(session)

    auto_enabled = auto_forward.is_enabled()

    text = messages.dashboard(
        source.title if source else None,
        destination.title if destination else None,
        stats["success"],
        auto_enabled,
    )
    markup = keyboards.main_menu(source is not None, destination is not None, auto_enabled)
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


async def toggle_auto_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    with get_session() as session:
        source = ChannelRepository.get_by_type(session, ChannelType.SOURCE)
        destination = ChannelRepository.get_by_type(session, ChannelType.DESTINATION)

    if source is None or destination is None:
        await update.callback_query.answer(
            "ابتدا کانال مبدأ و مقصد را تنظیم کنید.", show_alert=True
        )
        return

    client = await ensure_started()
    if auto_forward.is_enabled():
        await auto_forward.disable(client)
        await update.callback_query.answer("🔴 Auto-Forward خاموش شد")
    else:
        await auto_forward.enable(client)
        await update.callback_query.answer("🟢 Auto-Forward روشن شد")

    await show_dashboard(update, context, edit=True)
