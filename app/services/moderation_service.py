import hashlib
import json
import logging
import time
from dataclasses import replace

from app.guard_config import guard_settings
from app.services import ai_service
from app.services.ai_policy import AIProcessingError
from app.services.ai_settings import load_ai_settings
from app.services.context_manager import load_context, update_context
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime
from app.services.rule_guard import evaluate_rules, political_topics
from app.services.text_normalizer import normalize_text
from app.services.text_sanitizer import publication_is_clean, sanitize_text, username_replacement

logger = logging.getLogger(__name__)


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def record_decision(result: ModerationResult, chat_id, message_id, started: float, cached=False):
    counts = runtime.metrics
    counts["cache_hits" if cached else f"{result.source.lower()}_decisions"] += 1
    counts["blocked_messages"] += result.action == "DROP"
    counts["review_messages"] += result.action == "REVIEW"
    counts["sanitized_messages"] += result.label == Label.SANITIZE
    logger.info(
        "Guard decision chat_id=%s message_id=%s source=%s label=%s confidence=%.2f cached=%s elapsed=%.2fs ai_call_ratio=%.3f",
        chat_id,
        message_id,
        result.source,
        result.label.value,
        result.confidence,
        cached,
        time.monotonic() - started,
        runtime.snapshot()["ai_call_ratio"],
    )
    return result


async def moderate(chat_id: int | None, message_id: int | None, text: str) -> ModerationResult:
    started = time.monotonic()
    runtime.metrics["total_messages"] += 1
    config = load_ai_settings(ai_service.settings)
    limits = guard_settings
    if not config.enabled:
        return record_decision(
            ModerationResult(Label.OK, 1, text, "DISABLED"), chat_id, message_id, started
        )
    if len(text) > limits.max_input_chars:
        return record_decision(ModerationResult(Label.REVIEW, 1), chat_id, message_id, started)

    normalized = normalize_text(text, limits.max_candidates)
    context = load_context(chat_id, limits)
    provider = fingerprint((config.base_url, config.model, config.api_key))
    key = fingerprint(
        (
            chat_id,
            text,
            normalized.normalized,
            context,
            provider,
            vars(limits),
            ai_service.compact_prompt(),
            username_replacement(),
        )
    )
    cached = runtime.cached(key)
    if cached:
        return record_decision(cached, chat_id, message_id, started, cached=True)
    result = evaluate_rules(normalized, context)
    if result.confidence < limits.confidence_threshold:
        result = await ai_fallback(
            normalized, context, provider, config, limits, chat_id, message_id
        )
        if result.source == "UNAVAILABLE":
            return record_decision(result, chat_id, message_id, started)

    result = finalize(result, text)
    remember_context(result, chat_id, normalized.normalized, limits)
    runtime.remember(key, result, limits.cache_ttl_seconds, limits.cache_size)
    return record_decision(result, chat_id, message_id, started)


async def ai_fallback(normalized, context, provider, config, limits, chat_id, message_id):
    runtime.metrics["ai_fallbacks"] += 1
    if runtime.unavailable(provider):
        runtime.metrics["circuit_skips"] += 1
        return ModerationResult(Label.REVIEW, 0, source="UNAVAILABLE")
    runtime.metrics["ai_calls"] += 1
    logger.info("AI guard fallback triggered chat_id=%s message_id=%s", chat_id, message_id)
    reversed_words = " ".join(word[::-1] for word in normalized.normalized.split())
    variants = tuple(
        dict.fromkeys(
            value[:300]
            for value in (*normalized.candidates[1:2], reversed_words)
            if value != normalized.normalized
        )
    )
    try:
        result = await ai_service.classify(normalized.original, context, variants, config, limits)
        runtime.failures.pop(provider, None)
        return result
    except AIProcessingError:
        runtime.failed(provider, limits.failure_limit, limits.cooldown_seconds)
        return ModerationResult(Label.REVIEW, 0, source="UNAVAILABLE")


def finalize(result: ModerationResult, text: str) -> ModerationResult:
    if result.action == "PUBLISH":
        approved = result.text if result.label == Label.REWRITE else text
        clean = sanitize_text(approved, remove_links=True)
        if not publication_is_clean(clean):
            result = ModerationResult(Label.REVIEW, 0, source=result.source)
        else:
            result = replace(result, text=clean)
    return result


def remember_context(result: ModerationResult, chat_id, text: str, limits) -> None:
    if result.confidence >= limits.confidence_threshold and result.label not in {
        Label.INJECTION,
        Label.SPAM,
        Label.PORN,
        Label.REVIEW,
    }:
        change = dict(result.context_update)
        if result.label == Label.POLITICAL:
            change["political"] = True
            change["topics_add"] = political_topics(text)[: limits.max_topics]
        update_context(chat_id, change, text, limits)
