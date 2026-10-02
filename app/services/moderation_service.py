import hashlib
import json
import logging
import time
from dataclasses import replace

from app.guard_config import GuardSettings, guard_settings
from app.services import ai_service
from app.services.ai_settings import load_ai_settings
from app.services.context_manager import load_context, update_context
from app.services.guard.pipeline import PIPELINE_VERSION, GuardPipeline
from app.services.guard_models import Label, ModerationResult
from app.services.guard_profile import custom_policy, load_profile
from app.services.guard_runtime import runtime
from app.services.rule_guard import evaluate_rules, political_topics
from app.services.text_normalizer import normalize_text
from app.services.text_sanitizer import publication_is_clean, sanitize_text, username_replacement

logger = logging.getLogger(__name__)


def fingerprint(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def record_decision(result, chat_id, message_id, started, cached=False):
    counts = runtime.metrics
    counts["cache_hits" if cached else f"{result.source.lower()}_decisions"] += 1
    counts["blocked_messages"] += result.action == "DROP"
    counts["review_messages"] += result.action == "REVIEW"
    logger.info(
        "Guard decision chat_id=%s message_id=%s source=%s label=%s confidence=%.2f "
        "cached=%s elapsed=%.2fs ai_call_ratio=%.3f action=%s",
        chat_id, message_id, result.source, result.label.value, result.confidence,
        cached, time.monotonic() - started, runtime.snapshot()["ai_call_ratio"], result.action
    )
    return result


async def moderate(chat_id, message_id, text, *, draft=False):
    started = time.monotonic()
    runtime.metrics["total_messages"] += 1
    config = load_ai_settings(ai_service.settings)
    profile = load_profile(guard_settings, instructions=ai_service.settings.ai_guardrails)
    limits = GuardSettings(**profile["limits"])
    policy = ai_service.compact_prompt(profile)

    if not config.enabled:
        return record_decision(ModerationResult(Label.OK, 1, text, "DISABLED"), chat_id, message_id, started)

    if len(text) > limits.max_input_chars:
        return record_decision(
            ModerationResult(Label.REVIEW, 1, reason="input_too_long"),
            chat_id, message_id, started
        )

    normalized = normalize_text(text, limits.max_candidates)
    context = load_context(chat_id, limits)
    provider = fingerprint((config.base_url, config.model, config.api_key))
    key = fingerprint((
        PIPELINE_VERSION, chat_id, text, normalized.normalized,
        context, provider, config.fallback_model, config.news_grounding_enabled,
        config.news_allowed_domains, vars(limits), policy, username_replacement(),
    ))

    cached = runtime.cached(key) if not draft else None
    if cached:
        return record_decision(cached, chat_id, message_id, started, cached=True)

    result = evaluate_rules(normalized, context)
    grounding_attempted = False

    if (
        custom_policy(profile)
        or (draft and result.label != Label.ABUSE)
        or result.confidence < limits.confidence_threshold
    ):
        categories = {
            "political": Label.POLITICAL,
            "abuse": Label.ABUSE,
            "sexual": Label.PORN,
            "spam": Label.SPAM,
        }
        disabled = tuple(
            categories[name]
            for name, mode in profile["sensitivity"].items()
            if mode == "off"
        )
        pipeline = GuardPipeline(config, limits, context, policy, disabled_labels=disabled)
        result = await pipeline.run(text, draft=draft)
        grounding_attempted = pipeline.grounding_attempted
    else:
        result = finalize(result, text)

    if not grounding_attempted:
        remember_context(result, chat_id, normalized.normalized, limits)

    if not draft and not grounding_attempted and result.action == "PUBLISH":
        runtime.remember(key, result, limits.cache_ttl_seconds, limits.cache_size)

    return record_decision(result, chat_id, message_id, started)


def finalize(result, text):
    if result.action == "PUBLISH":
        approved = result.text if result.label == Label.REWRITE else text
        clean = sanitize_text(approved, remove_links=True)
        if not publication_is_clean(clean):
            result = ModerationResult(Label.REVIEW, 0, source=result.source, reason="unsafe_output")
        else:
            result = replace(result, text=clean)
    return result


def remember_context(result, chat_id, text, limits):
    if result.confidence >= limits.confidence_threshold and result.label not in {
        Label.INJECTION, Label.SPAM, Label.PORN, Label.ABUSE,
        Label.HATE, Label.THREAT, Label.REVIEW,
    }:
        change = dict(result.context_update)
        if result.label == Label.POLITICAL:
            change["political"] = True
            change["topics_add"] = political_topics(text)[: limits.max_topics]
        update_context(chat_id, change, text, limits)
