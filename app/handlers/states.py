from __future__ import annotations

from enum import Enum


class State(str, Enum):
    USERNAME_INPUT = "USERNAME_INPUT"
    MAIN_MENU = "MAIN_MENU"
    SOURCE_CHANNEL = "SOURCE_CHANNEL"
    DESTINATION_CHANNEL = "DESTINATION_CHANNEL"
    TRANSFER_MENU = "TRANSFER_MENU"
    RANGE_INPUT_START = "RANGE_INPUT_START"
    RANGE_INPUT_END = "RANGE_INPUT_END"
    IDS_INPUT = "IDS_INPUT"
    CONFIRM_TRANSFER = "CONFIRM_TRANSFER"
    TRANSFERRING = "TRANSFERRING"
    TRANSFER_RESULT = "TRANSFER_RESULT"
    SIGNATURE_INPUT = "SIGNATURE_INPUT"  # 👈 اضافه شد


# کلیدهای user_data
KEY_STATE = "state"
KEY_PENDING_CHANNEL_KIND = "pending_channel_kind"
KEY_PENDING_CHANNEL = "pending_channel"
KEY_RANGE_START = "range_start"
KEY_CURRENT_JOB_ID = "current_job_id"
KEY_PROGRESS_MESSAGE_ID = "progress_message_id"
KEY_LAST_MENU = "last_menu"


def set_state(user_data: dict, state: State) -> None:
    user_data[KEY_STATE] = state


def get_state(user_data: dict) -> State:
    return user_data.get(KEY_STATE, State.MAIN_MENU)


def reset(user_data: dict) -> None:
    for key in (
        KEY_PENDING_CHANNEL_KIND,
        KEY_PENDING_CHANNEL,
        KEY_RANGE_START,
        "range_end",
        "explicit_ids",
    ):
        user_data.pop(key, None)
    set_state(user_data, State.MAIN_MENU)
