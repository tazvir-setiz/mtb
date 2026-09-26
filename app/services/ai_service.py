import asyncio
import json
import logging
import time

import httpx

from app.config import BASE_DIR, settings
from app.guard_config import GuardSettings
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_settings import AISettings
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
    text: str, context: dict, candidates: tuple[str, ...], config: AISettings, limits: GuardSettings
):
    if not config.api_key:
        logger.error("AI guard failure reason=missing_api_key action=REVIEW")
        raise AIProcessingError("AI API key is missing")
    user_data = {"ctx": context, "msg": text}
    if candidates:
        user_data["variants"] = list(candidates[:2])
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": compact_prompt()},
            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": limits.max_output_tokens,
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
                response = await client.post(
                    config.base_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {config.api_key}"},
                )
                response.raise_for_status()
                choice = response.json()["choices"][0]
                if choice.get("finish_reason") in {"length", "content_filter", "tool_calls"}:
                    raise AIProcessingError("Guard response was not completed")
                result = validate_output(choice["message"]["content"], limits)
        logger.info(
            "AI guard response label=%s confidence=%.2f elapsed=%.2fs",
            result.label.value,
            result.confidence,
            time.monotonic() - started,
        )
        return result
    except AIProcessingError:
        logger.warning(
            "AI guard failure reason=invalid_or_incomplete_output elapsed=%.2fs action=REVIEW",
            time.monotonic() - started,
        )
        raise
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        logger.warning(
            "AI guard failure type=%s status=%s elapsed=%.2fs",
            type(exc).__name__,
            status,
            time.monotonic() - started,
        )
        raise AIProcessingError("AI service unavailable or response invalid") from None


async def apply_ai_guardrails(
    html_text: str, *, chat_id: int | None = None, message_id: int | None = None
) -> str:
    from app.services.moderation_service import moderate

    result = await moderate(chat_id, message_id, html_text)
    if result.action == "DROP":
        return "__DROP__"
    if result.action == "REVIEW":
        raise AIReviewRequired("Guard decision requires review")
    return result.text or ""
