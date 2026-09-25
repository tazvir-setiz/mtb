"""Callback destinations. Keep callback names aligned with app/ui/buttons/."""

from functools import partial
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers import dashboard, destination, source, statistics, transfer
from app.handlers import settings as settings_handlers

CallbackHandler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

CALLBACK_ROUTES: dict[tuple[str, str], CallbackHandler] = {
    ("menu", "source"): partial(source.show_channel_prompt, kind="source"),
    ("menu", "destination"): partial(source.show_channel_prompt, kind="destination"),
    ("menu", "transfer"): transfer.show_transfer_menu,
    ("menu", "recent"): statistics.show_recent,
    ("menu", "stats"): statistics.show_statistics,
    ("menu", "settings"): settings_handlers.show_settings,
    ("menu", "help"): settings_handlers.show_help,
    ("menu", "auto_toggle"): dashboard.toggle_auto_forward,
    ("nav", "home"): partial(dashboard.show_dashboard, edit=True),
    ("nav", "cancel"): partial(dashboard.show_dashboard, edit=True),
    ("nav", "back"): partial(dashboard.show_dashboard, edit=True),
    ("source", "confirm"): partial(source.handle_confirm, kind="source"),
    ("source", "change"): partial(source.handle_change, kind="source"),
    ("destination", "confirm"): partial(source.handle_confirm, kind="destination"),
    ("destination", "change"): partial(source.handle_change, kind="destination"),
    ("destination", "retry"): destination.handle_destination_retry,
    ("destination", "help"): destination.handle_destination_help,
    ("transfer", "range"): transfer.start_range_flow,
    ("transfer", "ids"): transfer.start_ids_flow,
    ("transfer", "new"): transfer.start_new_messages_flow,
    ("transfer", "edit"): transfer.edit_range,
    ("transfer", "confirm"): transfer.confirm_and_start,
    ("transfer", "pause"): transfer.pause_transfer,
    ("transfer", "resume"): transfer.resume_transfer,
    ("transfer", "restart"): transfer.show_transfer_menu,
    ("transfer", "errors"): transfer.show_errors,
    ("transfer", "retry"): transfer.retry_failed_messages,
    ("transfer", "start"): transfer.show_confirm_from_range,
    ("stats", "refresh"): statistics.refresh_statistics,
    ("stats", "clear"): statistics.ask_clear_statistics,
    ("stats", "clear_confirm"): statistics.clear_statistics_handler,
    ("settings", "delay"): settings_handlers.show_delay_info,
    ("settings", "clear_data"): settings_handlers.ask_clear_data,
    ("settings", "clear_data_confirm"): settings_handlers.clear_data,
    ("settings", "signature"): settings_handlers.ask_signature,
    ("settings", "clear_sig"): settings_handlers.clear_signature,
}
