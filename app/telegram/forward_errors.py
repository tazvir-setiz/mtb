"""Translate Telegram and transport errors into user-facing categories."""

from enum import Enum

from telethon.errors import (
    ChatAdminRequiredError,
    ChatForwardsRestrictedError,
    FloodWaitError,
    MessageIdInvalidError,
    UserBannedInChannelError,
)
from telethon.errors.rpcerrorlist import ChatWriteForbiddenError


class ForwardErrorType(str, Enum):
    FLOOD_WAIT = "flood_wait"
    MESSAGE_NOT_FOUND = "message_not_found"
    CHAT_NOT_FOUND = "chat_not_found"
    PERMISSION_DENIED = "permission_denied"
    FORBIDDEN = "forbidden"
    PROTECTED_CONTENT = "protected_content"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


FRIENDLY_ERRORS: dict[ForwardErrorType, str] = {
    ForwardErrorType.FLOOD_WAIT: "⏳ محدودیت موقت Telegram (FloodWait)",
    ForwardErrorType.MESSAGE_NOT_FOUND: "⚠️ پیام یافت نشد یا حذف شده است",
    ForwardErrorType.CHAT_NOT_FOUND: "⚠️ کانال یافت نشد",
    ForwardErrorType.PERMISSION_DENIED: "⚠️ دسترسی کافی نیست",
    ForwardErrorType.FORBIDDEN: "⚠️ ارسال پیام مجاز نیست",
    ForwardErrorType.PROTECTED_CONTENT: "🔒 محتوای محافظت‌شده",
    ForwardErrorType.NETWORK_ERROR: "🌐 خطای شبکه",
    ForwardErrorType.UNKNOWN: "⚠️ خطای نامشخص",
}


def classify_error(exc: Exception) -> ForwardErrorType:
    if isinstance(exc, FloodWaitError):
        return ForwardErrorType.FLOOD_WAIT
    if isinstance(exc, MessageIdInvalidError):
        return ForwardErrorType.MESSAGE_NOT_FOUND
    if isinstance(exc, (ChatAdminRequiredError, ChatWriteForbiddenError)):
        return ForwardErrorType.PERMISSION_DENIED
    if isinstance(exc, ChatForwardsRestrictedError):
        return ForwardErrorType.PROTECTED_CONTENT
    if isinstance(exc, UserBannedInChannelError):
        return ForwardErrorType.FORBIDDEN
    if isinstance(exc, ValueError) and "Cannot find" in str(exc):
        return ForwardErrorType.CHAT_NOT_FOUND
    if isinstance(exc, (ConnectionError, OSError)):
        return ForwardErrorType.NETWORK_ERROR
    return ForwardErrorType.UNKNOWN
