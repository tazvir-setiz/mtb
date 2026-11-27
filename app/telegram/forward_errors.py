from enum import Enum

from telethon.errors import (
    ChatAdminRequiredError,
    ChatForwardsRestrictedError,
    FloodWaitError,
    MessageIdInvalidError,
    UserBannedInChannelError,
)
from telethon.errors.rpcerrorlist import ChatWriteForbiddenError

try:
    from telegram.error import (
        BadRequest as PTBBadRequest,
        Forbidden as PTBForbidden,
        NetworkError as PTBNetworkError,
        RetryAfter as PTBRetryAfter,
        TimedOut as PTBTimedOut,
    )
except ImportError:  # pragma: no cover
    PTBBadRequest = PTBForbidden = PTBNetworkError = PTBRetryAfter = PTBTimedOut = ()  # type: ignore[assignment,misc]

from app.services.ai_policy import AIProcessingError, AIReviewRequired


class ForwardErrorType(str, Enum):
    FLOOD_WAIT = "flood_wait"
    MESSAGE_NOT_FOUND = "message_not_found"
    CHAT_NOT_FOUND = "chat_not_found"
    PERMISSION_DENIED = "permission_denied"
    FORBIDDEN = "forbidden"
    PROTECTED_CONTENT = "protected_content"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"
    AI_REVIEW = "ai_review"
    AI_ERROR = "ai_error"


FRIENDLY_ERRORS: dict[ForwardErrorType, str] = {
    ForwardErrorType.AI_REVIEW: "🔎 منتظر تصمیم مدیر؛ از اعلان بررسی یا /reviews تأیید یا رد کنید.",
    ForwardErrorType.AI_ERROR: "🤖 خطای پالایش هوشمند؛ برای جلوگیری از ارسال متن خام، منتشر نشد.",
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
    if isinstance(exc, AIReviewRequired):
        return ForwardErrorType.AI_REVIEW
    if isinstance(exc, AIProcessingError):
        return ForwardErrorType.AI_ERROR
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
    if isinstance(exc, (ConnectionError, OSError, PTBTimedOut, PTBNetworkError)):
        return ForwardErrorType.NETWORK_ERROR
    if isinstance(exc, PTBRetryAfter):
        return ForwardErrorType.FLOOD_WAIT
    if isinstance(exc, PTBForbidden):
        return ForwardErrorType.PERMISSION_DENIED
    if isinstance(exc, PTBBadRequest):
        msg = str(exc).lower()
        if any(k in msg for k in ("chat not found", "peer_id_invalid", "channel_invalid")):
            return ForwardErrorType.CHAT_NOT_FOUND
        if any(k in msg for k in ("not enough rights", "need administrator rights", "no rights to send", "chat_write_forbidden")):
            return ForwardErrorType.PERMISSION_DENIED
        if any(k in msg for k in ("protected", "forwards_restricted")):
            return ForwardErrorType.PROTECTED_CONTENT
        return ForwardErrorType.MESSAGE_NOT_FOUND
    return ForwardErrorType.UNKNOWN
