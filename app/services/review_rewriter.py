import logging

from app.guard_config import guard_settings
from app.services import ai_service
from app.services.ai_policy import AIReviewRequired
from app.services.ai_settings import load_ai_settings
from app.services.context_manager import load_context
from app.services.guard_models import Label
from app.services.moderation_service import finalize
from app.services.rule_guard import evaluate_rules
from app.services.text_normalizer import normalize_text

logger = logging.getLogger(__name__)


async def rewrite_draft(text, *, chat_id=None, message_id=None):
    limits = guard_settings
    config = load_ai_settings()
    if not config.enabled:
        raise AIReviewRequired("ai_disabled")
    if len(text) > limits.max_input_chars:
        raise AIReviewRequired("input_too_long")
    context = load_context(chat_id, limits)
    local = evaluate_rules(normalize_text(text), context)
    if local.action == "DROP" and local.confidence >= limits.confidence_threshold:
        logger.info(
            "Review rewrite message_id=%s local_label=%s action=DROP", message_id, local.label.value
        )
        return "__DROP__"
    logger.info("Review rewrite started message_id=%s input_chars=%d", message_id, len(text))
    result = await ai_service.classify(text, context, (), config, limits, rewrite=True)
    if result.action == "DROP":
        return "__DROP__"
    if result.label != Label.REWRITE:
        raise AIReviewRequired(result.reason or "rewrite_failed")
    result = finalize(result, text)
    if result.action != "PUBLISH" or not result.text:
        raise AIReviewRequired("rewrite_failed")
    verified = await ai_service.classify(result.text, context, (), config, limits)
    if verified.label not in {Label.OK, Label.SANITIZE}:
        raise AIReviewRequired("rewrite_failed")
    logger.info("Review rewrite ready message_id=%s output_chars=%d", message_id, len(result.text))
    return result.text
