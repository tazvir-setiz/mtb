from app.services.ai_policy import AIReviewRequired
from app.services.ai_settings import load_ai_settings
from app.services.ai_transport import AIRequestError
from app.services.moderation_service import moderate


async def rewrite_draft(text, *, chat_id=None, message_id=None):
    if not load_ai_settings().enabled:
        raise AIReviewRequired("ai_disabled")
    result = await moderate(chat_id, message_id, text, draft=True)
    if result.action == "DROP":
        return "__DROP__"
    if result.source == "UNAVAILABLE":
        raise AIRequestError(result.reason)
    if result.action == "REVIEW":
        raise AIReviewRequired(result.reason or "rewrite_failed")
    return result.text
