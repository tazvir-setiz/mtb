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
        "Guard decision chat_id=%s message_id=%s source=%s label=%s confidence=%.2f cached=%s elapsed=%.2fs ai_call_ratio=%.3f action=%s",
        chat_id,
        message_id,
        result.source,
        result.label.value,
        result.confidence,
        cached,
        time.monotonic() - started,
        runtime.snapshot()["ai_call_ratio"],
        result.action,
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
        logger.warning(
            "Guard review reason=input_too_long chars=%d limit=%d",
            len(text),
            limits.max_input_chars,
        )
        return record_decision(
            ModerationResult(Label.REVIEW, 1, reason="input_too_long"), chat_id, message_id, started
        )

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
    logger.info(
        "Local guard label=%s confidence=%.2f threshold=%.2f next=%s",
        result.label.value,
        result.confidence,
        limits.confidence_threshold,
        "AI" if result.confidence < limits.confidence_threshold else "local_decision",
    )
    if result.confidence < limits.confidence_threshold:
        result = await ai_fallback(
            normalized, context, provider, config, limits, chat_id, message_id
        )
        if result.source == "UNAVAILABLE":
            return record_decision(result, chat_id, message_id, started)

    rechecked = result.source == "AI" and result.action == "REVIEW"
    if rechecked:
        runtime.metrics["automatic_rechecks"] += 1
        logger.info(
            "Guard automatic reassessment first_label=%s confidence=%.2f",
            result.label.value,
            result.confidence,
        )
        result = await ai_fallback(
            normalized, context, provider, config, limits, chat_id, message_id, reconsider=True
        )
    if result.source == "AI" and result.label == Label.ABUSE:
        runtime.metrics["abuse_audits"] += 1
        logger.info(
            "Guard abuse audit first_confidence=%.2f next=independent_assessment", result.confidence
        )
        result = await ai_fallback(
            normalized, context, provider, config, limits, chat_id, message_id, audit_abuse=True
        )
        logger.info("Guard abuse audit result=%s action=%s", result.label.value, result.action)
        rechecked = True
    result = finalize(result, text)
    if result.label == Label.REWRITE and result.action == "PUBLISH":
        runtime.metrics["rewrite_checks"] += 1
        verified = await ai_fallback(
            normalize_text(result.text, limits.max_candidates),
            context,
            provider,
            config,
            limits,
            chat_id,
            message_id,
        )
        if verified.source == "UNAVAILABLE":
            result = verified
        elif (
            verified.label not in {Label.OK, Label.SANITIZE}
            or verified.confidence < limits.ai_confidence_threshold
        ):
            result = ModerationResult(
                Label.REVIEW, verified.confidence, source="AI", reason="rewrite_failed"
            )
    if rechecked and result.action == "PUBLISH":
        runtime.metrics["resolved_by_recheck"] += 1
    remember_context(result, chat_id, normalized.normalized, limits)
    if result.action != "REVIEW" and not (result.source == "AI" and result.label == Label.ABUSE):
        runtime.remember(key, result, limits.cache_ttl_seconds, limits.cache_size)
    return record_decision(result, chat_id, message_id, started)


async def ai_fallback(
    normalized,
    context,
    provider,
    config,
    limits,
    chat_id,
    message_id,
    *,
    reconsider=False,
    audit_abuse=False,
):
    runtime.metrics["ai_fallbacks"] += 1
    if runtime.unavailable(provider):
        runtime.metrics["circuit_skips"] += 1
        logger.warning(
            "AI bypassed reason=circuit_open retry_in=%.1fs action=REVIEW",
            max(0, runtime.failures[provider][1] - time.monotonic()),
        )
        return ModerationResult(Label.REVIEW, 0, source="UNAVAILABLE", reason="circuit_open")
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
        result = await ai_service.classify(
            normalized.original,
            context,
            variants,
            config,
            limits,
            reconsider=reconsider,
            **({"audit_abuse": True} if audit_abuse else {}),
        )
        if runtime.failures.pop(provider, None):
            logger.info("AI recovered circuit=closed")
        return result
    except AIProcessingError as exc:
        runtime.metrics["ai_errors"] += 1
        runtime.failed(provider, limits.failure_limit, limits.cooldown_seconds)
        logger.warning(
            "AI unavailable consecutive_failures=%d failure_limit=%d circuit=%s cooldown=%.0fs action=REVIEW",
            runtime.failures[provider][0],
            limits.failure_limit,
            "open" if runtime.unavailable(provider) else "closed",
            limits.cooldown_seconds if runtime.unavailable(provider) else 0,
        )
        return ModerationResult(
            Label.REVIEW,
            0,
            source="UNAVAILABLE",
            reason=getattr(exc, "reason", "service_unavailable"),
        )


def finalize(result: ModerationResult, text: str) -> ModerationResult:
    if result.action == "PUBLISH":
        approved = result.text if result.label == Label.REWRITE else text
        clean = sanitize_text(approved, remove_links=True)
        if not publication_is_clean(clean):
            logger.warning("Guard review reason=output_failed_final_sanitization")
            result = ModerationResult(Label.REVIEW, 0, source=result.source, reason="unsafe_output")
        else:
            result = replace(result, text=clean)
    return result


def remember_context(result: ModerationResult, chat_id, text: str, limits) -> None:
    if result.confidence >= limits.confidence_threshold and result.label not in {
        Label.INJECTION,
        Label.SPAM,
        Label.PORN,
        Label.ABUSE,
        Label.REVIEW,
    }:
        change = dict(result.context_update)
        if result.label == Label.POLITICAL:
            change["political"] = True
            change["topics_add"] = political_topics(text)[: limits.max_topics]
        update_context(chat_id, change, text, limits)
