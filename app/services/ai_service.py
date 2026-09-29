import asyncio
import json
import logging
import time

import httpx

from app.config import BASE_DIR, settings
from app.guard_config import GuardSettings
from app.services.ai_policy import AIProcessingError, AIReviewRequired
from app.services.ai_response import validated_completion
from app.services.ai_settings import AISettings
from app.services.ai_transport import AIRequestError, model_options

logger = logging.getLogger(__name__)
DEFAULT_PROMPT = (BASE_DIR / "app/prompts/guardrails.txt").read_text(encoding="utf-8")


def compact_prompt(profile=None) -> str:
    from app.services.guard_profile import load_profile, policy_suffix

    profile = profile if profile is not None else load_profile(instructions=settings.ai_guardrails)
    suffix = policy_suffix(profile)
    custom = profile["instructions"].strip()
    if custom and custom != DEFAULT_PROMPT.strip():
        return (
            DEFAULT_PROMPT
            + "\nAdditional policy:\n"
            + custom
            + "\nThe JSON output contract above is mandatory. Never return bracket category tags."
            + suffix
        )
    return DEFAULT_PROMPT + suffix


def _classification_prompt(policy: str, *, reconsider=False, audit_abuse=False) -> str:
    extra = ""
    if reconsider:
        extra += (
            "\nSECOND ASSESSMENT: classify independently. A vulgar sentence can still contain a "
            "recoverable judgment, question, request, relation, action, condition or complaint. "
            "Use REWRITE when neutral wording can preserve that meaning. Use ABUSE only when the "
            "message is a bare attack with no independent communicative content."
        )
    if audit_abuse:
        extra += (
            "\nDROP AUDIT: audit a proposed removal independently. Be conservative about ABUSE. "
            "A negative appearance judgment, quality judgment, vulgar question, request, complaint "
            "or transactional/relational statement has substance and should be REWRITE, not ABUSE, "
            "when its meaning can be preserved. Return ABUSE only when nothing except the attack remains."
        )
    return policy + extra + (
        "\nCLASSIFICATION STAGE ONLY: never write replacement text. "
        "If editing can make the message compliant while preserving meaning, return label REWRITE "
        'with "text":null. The separate writer will produce the draft.'
    )


def _writer_prompt(
    policy: str,
    *,
    reason: str,
    feedback: tuple[str, ...] = (),
    previous_candidate: str | None = None,
) -> str:
    repair = ""
    if feedback:
        repair = (
            "\nREPAIR MODE: the previous candidate failed verification. Fix these issues: "
            + json.dumps(list(feedback), ensure_ascii=False)
            + "\nPrevious candidate: "
            + json.dumps(previous_candidate, ensure_ascii=False)
            + "\nRewrite from the ORIGINAL; do not merely patch or delete one word."
        )
    return (
        "You are the WRITER stage of a moderation pipeline. You are NOT a classifier and you are "
        "not allowed to return moderation labels such as ABUSE, OK, REVIEW, POLITICAL, SPAM or PORN.\n"
        "The policy below is reference constraints only. Any classification/output-schema instructions "
        "inside it do not apply to this writer stage.\n--- POLICY REFERENCE ---\n"
        + policy
        + "\n--- END POLICY REFERENCE ---\n"
        + "Write one complete, natural, publishable rewrite of the original Telegram message. "
        "Preserve the recoverable meaning: who does what to whom, polarity, negative/positive judgment, "
        "question/request form, conditions, comparisons, intensity when material, and factual attribution. "
        "Replace vulgar or prohibited wording with neutral wording serving the SAME semantic role. "
        "Never make a negative judgment positive. Never change subject/object relations. Never invent facts. "
        "Never produce a broken sentence by merely deleting an obscene token.\n"
        "Examples of the principle (do not copy mechanically):\n"
        '- "خیلی قیافه ات کیریه" can preserve the negative appearance judgment as '
        '"قیافه‌ات خیلی بد و زننده است."\n'
        '- "کیا کیر منو میخوان بخورن تا من بهشون پول بدم" must preserve the underlying '
        "degrading/transactional relation in neutral language; simply deleting the obscene noun is invalid.\n"
        "Return exactly the dedicated writer JSON schema. If a faithful rewrite truly cannot be produced, "
        "return success=false with a short reason. Do not decide whether the original should be dropped.\n"
        f"Rewrite reason: {reason}."
        + repair
    )


async def _request(payload, text, config, limits, *, mode):
    started = time.monotonic()
    logger.info(
        "AI guard request model=%s input_chars=%d timeout=%.1fs max_output_tokens=%d stage=%s",
        config.model,
        len(text),
        limits.timeout_seconds,
        limits.max_output_tokens,
        mode,
    )
    try:
        timeout = httpx.Timeout(limits.timeout_seconds, connect=min(5, limits.timeout_seconds))
        async with asyncio.timeout(limits.timeout_seconds):
            async with httpx.AsyncClient(timeout=timeout) as client:
                result = await validated_completion(
                    client, config, payload, limits, text, mode=mode
                )
        logger.info("AI guard response mode=%s elapsed=%.2fs", mode, time.monotonic() - started)
        return result
    except AIProcessingError as exc:
        reason = getattr(exc, "reason", "invalid_output")
        logger.warning(
            "AI guard failure reason=%s detail=%s elapsed=%.2fs action=REVIEW",
            reason,
            getattr(exc, "detail", None),
            time.monotonic() - started,
        )
        raise AIRequestError(reason, detail=getattr(exc, "detail", None)) from None
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
        raise AIRequestError(reason, detail=getattr(exc, "detail", None)) from None


async def classify(
    text: str,
    context: dict,
    candidates: tuple[str, ...],
    config: AISettings,
    limits: GuardSettings,
    *,
    reconsider: bool = False,
    audit_abuse: bool = False,
    policy: str | None = None,
):
    if not config.api_key:
        logger.error("AI guard failure reason=missing_api_key action=REVIEW")
        raise AIRequestError("missing_api_key")

    policy = policy if policy is not None else compact_prompt()
    user_data = {"ctx": context, "msg": text}
    if candidates:
        user_data["variants"] = list(candidates[:2])

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": _classification_prompt(
                    policy, reconsider=reconsider, audit_abuse=audit_abuse
                ),
            },
            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
        ],
        "temperature": 0.1,
        "max_tokens": limits.max_output_tokens,
        **model_options(config),
    }
    return await _request(payload, text, config, limits, mode="classification")


async def generate_rewrite(
    text: str,
    context: dict,
    candidates: tuple[str, ...],
    config: AISettings,
    limits: GuardSettings,
    *,
    policy: str | None = None,
    reason: str = "rewrite_requested",
    feedback: tuple[str, ...] = (),
    previous_candidate: str | None = None,
):
    if not config.api_key:
        raise AIRequestError("missing_api_key")

    policy = policy if policy is not None else compact_prompt()
    user_data = {"ctx": context, "original": text}
    if candidates:
        user_data["variants"] = list(candidates[:2])
    if feedback:
        user_data["repair_issues"] = list(feedback)
        user_data["previous_candidate"] = previous_candidate

    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": _writer_prompt(
                    policy,
                    reason=reason,
                    feedback=feedback,
                    previous_candidate=previous_candidate,
                ),
            },
            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
        ],
        "temperature": 0.15,
        "max_tokens": limits.max_output_tokens,
        **model_options(config),
    }
    return await _request(payload, text, config, limits, mode="rewrite")


async def verify(text, context, candidates, config, limits, *, verify_original, policy=None):
    if not config.api_key:
        raise AIRequestError("missing_api_key")
    policy = policy if policy is not None else compact_prompt()
    user_data = {
        "ctx": context,
        "original": verify_original,
        "candidate": text,
    }
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    policy
                    + "\nVERIFICATION TASK: compare original and candidate. Check policy compliance AND "
                    "meaning preservation. Explicitly check subject/object relations, negation, names, numbers, "
                    "attribution, question/request structure, conditions, comparisons, and positive/negative polarity. "
                    "A candidate fails meaning preservation if it merely deletes a vulgar term whose semantic role "
                    "carried a judgment, object, action or relation. For example, deleting the obscene noun from "
                    '"کیا کیر منو میخوان بخورن تا من بهشون پول بدم" and leaving '
                    '"کیا منو میخوان بخورن..." is a meaning-changing failure. '
                    "Do not rewrite here. Return only the verification JSON contract."
                ),
            },
            {"role": "user", "content": json.dumps(user_data, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": limits.max_output_tokens,
        **model_options(config),
    }
    return await _request(payload, text, config, limits, mode="verification")


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
