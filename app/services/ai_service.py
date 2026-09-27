import asyncio
import json
import logging
import time

import httpx

from app.config import BASE_DIR, settings
from app.guard_config import GuardSettings
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_settings import AISettings
from app.services.ai_transport import AIRequestError, model_options, post_completion
from app.services.output_validator import validate_output

logger = logging.getLogger(__name__)
DEFAULT_PROMPT = (BASE_DIR / "app/prompts/guardrails.txt").read_text(encoding="utf-8")


def compact_prompt() -> str:
    custom = settings.ai_guardrails.strip()
    if custom and custom != DEFAULT_PROMPT.strip() and len(custom) <= 800:
        return (
            DEFAULT_PROMPT
            + "\nAdditional policy:\n"
            + custom
            + "\nThe JSON output contract above is mandatory. Never return bracket category tags."
        )
    return DEFAULT_PROMPT


async def classify(
    text: str,
    context: dict,
    candidates: tuple[str, ...],
    config: AISettings,
    limits: GuardSettings,
    *,
    reconsider: bool = False,
    rewrite: bool = False,
):
    if not config.api_key:
        logger.error("AI guard failure reason=missing_api_key action=REVIEW")
        raise AIRequestError("missing_api_key")
    user_data = {"ctx": context, "msg": text}
    if candidates:
        user_data["variants"] = list(candidates[:2])
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": compact_prompt()
                + (
                    "\nTask: write a revised draft for the administrator, not just a classification. "
                    "Return REWRITE with the full revised Telegram HTML text when substantive meaning "
                    "can be preserved in compliance with every rule. Improve wording even if the input "
                    "is already publishable. Preserve facts and attribution; never invent a message. "
                    "For pure insults with nothing to preserve return ABUSE. "
                    "If faithful compliant rewriting is impossible, return REVIEW or a drop label."
                    if rewrite
                    else ""
                )
                + (
                    "\nSecond assessment: distinguish neutral reporting/quoted statements from the author's advocacy. "
                    "Try REWRITE for political advocacy as well as abuse if removing slogans, incitement or hostile tone "
                    "can produce neutral compliant reporting. Preserve supported facts, attribution and core meaning; "
                    "never invent facts or reverse a claim. "
                    "Do not invent missing context or approve merely because this is a second assessment. "
                    "Use ABUSE to drop pure insults with no substantive meaning to preserve. "
                    "Otherwise use REVIEW/POLITICAL if no faithful compliant rewrite is possible."
                    if reconsider
                    else ""
                ),
            },
            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": limits.max_output_tokens,
        **model_options(config),
    }
    started = time.monotonic()
    logger.info(
        "AI guard request model=%s input_chars=%d timeout=%.1fs max_output_tokens=%d",
        config.model,
        len(text),
        limits.timeout_seconds,
        limits.max_output_tokens,
    )
    try:
        timeout = httpx.Timeout(limits.timeout_seconds, connect=min(5, limits.timeout_seconds))
        async with asyncio.timeout(limits.timeout_seconds):
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await post_completion(client, config, payload)
                data = response.json()
                choice = data["choices"][0]
                usage = data.get("usage") or {}
                logger.info(
                    "AI completion finish=%s output_tokens=%s reasoning_tokens=%s thinking=%s",
                    choice.get("finish_reason"),
                    usage.get("completion_tokens"),
                    (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    payload.get("thinking", {}).get("type", "provider_default"),
                )
                if choice.get("finish_reason") in {"length", "content_filter", "tool_calls"}:
                    raise AIRequestError(
                        "response_truncated"
                        if choice.get("finish_reason") == "length"
                        else "provider_refusal"
                    )
                result = validate_output(choice["message"]["content"], limits)
        logger.info(
            "AI guard response label=%s confidence=%.2f elapsed=%.2fs",
            result.label.value,
            result.confidence,
            time.monotonic() - started,
        )
        return result
    except AIProcessingError as exc:
        reason = getattr(exc, "reason", "invalid_output")
        logger.warning(
            "AI guard failure reason=%s elapsed=%.2fs action=REVIEW",
            reason,
            time.monotonic() - started,
        )
        raise AIRequestError(reason) from None
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        reason = (
            "timeout"
            if isinstance(exc, (TimeoutError, httpx.TimeoutException))
            else "invalid_credentials"
            if status in {401, 403}
            else "rate_limit"
            if status == 429
            else "bad_request"
            if status in {400, 404, 422}
            else "provider_error"
            if status is not None
            else "connection_error"
            if isinstance(exc, httpx.TransportError)
            else "invalid_output"
        )
        logger.warning(
            "AI guard failure type=%s status=%s elapsed=%.2fs",
            type(exc).__name__,
            status,
            time.monotonic() - started,
        )
        raise AIRequestError(reason) from None


async def apply_ai_guardrails(
    html_text: str, *, chat_id: int | None = None, message_id: int | None = None
) -> str:
    from app.services.moderation_service import moderate

    result = await moderate(chat_id, message_id, html_text)
    if result.action == "DROP":
        return "__DROP__"
    if result.action == "REVIEW":
        raise AIReviewRequired(result.reason or result.label.value.lower())
    return result.text or ""
