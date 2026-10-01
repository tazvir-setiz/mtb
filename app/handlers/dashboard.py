from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    SettingsRepository,
)
from app.handlers.states import State, reset, set_state
from app.services.ai_settings import load_ai_settings
from app.telegram import auto_forward
from app.telegram.client import ensure_started
from app.ui import keyboards, messages


def _channel_summary(channels) -> str | None:
    if not channels:
        return None
    if len(channels) == 1:
        return channels[0].title
    return f"{channels[0].title} + {len(channels) - 1} کانال دیگر"


def _dashboard_content() -> tuple[str, object]:
    with get_session() as session:
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)
        stats = ForwardedMessageRepository.stats(session)
        signature = SettingsRepository.get(session, "signature_text")

    auto_enabled = auto_forward.is_enabled()

    text = messages.dashboard(
        _channel_summary(sources),
        _channel_summary(destinations),
        stats["success"],
        auto_enabled,
        ai_enabled=load_ai_settings(settings).enabled,
        signature_enabled=bool(signature),
    )
    markup = keyboards.main_menu(
        source_ready=bool(sources),
        destination_ready=bool(destinations),
        auto_forward_enabled=auto_enabled,
        source_id=sources[0].telegram_id if len(sources) == 1 else None,
        destination_id=destinations[0].telegram_id if len(destinations) == 1 else None,
    )
    return text, markup


async def show_dashboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    edit: bool = False,
) -> None:
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
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)

    if not sources or not destinations:
        await update.callback_query.answer(
            "ابتدا حداقل یک کانال مبدأ و یک کانال مقصد تنظیم کنید.",
            show_alert=True,
        )
        return

    client = await ensure_started()
    if auto_forward.is_enabled():
        await auto_forward.disable(client)
        await update.callback_query.message.reply_text("⚪ انتقال خودکار خاموش شد.")
    else:
        if not await auto_forward.enable(client):
            await update.callback_query.message.reply_text(
                "⚠️ انتقال خودکار فعال نشد. کانال‌ها را بررسی کنید."
            )
            return

    await show_auto_forward(update, context)


async def show_auto_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset(context.user_data)
    with get_session() as session:
        sources = ChannelRepository.get_all_by_type(session, ChannelType.SOURCE)
        destinations = ChannelRepository.get_all_by_type(session, ChannelType.DESTINATION)
    if not sources or not destinations:
        await show_dashboard(update, context, edit=True)
        return
    enabled = auto_forward.is_enabled()
    source_text = "\n".join(f"• {escape(channel.title[:80])}" for channel in sources[:10])
    destination_text = "\n".join(f"• {escape(channel.title[:80])}" for channel in destinations[:10])
    if len(sources) > 10:
        source_text += f"\n… و {len(sources) - 10} مبدأ دیگر"
    if len(destinations) > 10:
        destination_text += f"\n… و {len(destinations) - 10} مقصد دیگر"
    await update.callback_query.edit_message_text(
        "⚡ <b>انتقال خودکار پیام‌های جدید</b>\n\n"
        f"<b>📥 مبداها ({len(sources)})</b>\n{source_text}\n\n"
        f"<b>📤 مقصدها ({len(destinations)})</b>\n{destination_text}\n\n"
        f"وضعیت: <b>{'🟢 روشن' if enabled else '⚪ خاموش'}</b>\n\n"
        "هر پیام جدید از هر مبدأ، به همه مقصدهای تنظیم‌شده ارسال می‌شود.\n"
        "برای پیام‌های قبلی از «انتقال پیام‌ها» استفاده کنید.",
        reply_markup=keyboards.auto_forward_menu(enabled),
    )
