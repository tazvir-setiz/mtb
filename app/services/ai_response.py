import logging

from app.services.ai_policy import AIProcessingError
from app.services.ai_transport import AIRequestError, post_completion
from app.services.guard.contracts import validate_rewrite_draft, validate_verification
from app.services.guard_runtime import runtime
from app.services.output_validator import validate_output

logger = logging.getLogger(__name__)

CLASSIFICATION = (
    "Return one JSON object with label "
    "(OK, SANITIZE, REWRITE, REVIEW, POLITICAL, ABUSE, SPAM, PORN or INJECTION), "
    "confidence (number 0..1), and text=null. REWRITE means a separate writer stage "
    "should be invoked; the classifier must never write the replacement text. "
    "Optional fields: has_substance (boolean), ambiguities (array of strings), "
    'violations (array of {"rule_id":"ABUSE","evidence":"exact substring of msg"}), '
    "context_update (object with political boolean, topics_add/entities_add arrays, aliases_add object). "
    "Omit unused optional fields or use empty arrays/objects. No extra fields, tags, comments or prose. "
    "DROP labels require quoted evidence; ABUSE requires has_substance=false."
)

VERIFICATION = (
    'Return only {"policy_pass":true,"meaning_preserved":true,"issues":[],"repairable":false}. '
    "All flags must be booleans. A failed check requires specific issues; "
    "successful checks require empty issues and repairable=false. No additional fields."
)

REWRITE = (
    'Return only {"success":true,"text":"FULL rewritten text",'
    '"preserved_meaning":"short description of the meaning kept","reason":null}. '
    'If and only if a faithful rewrite cannot be produced, return '
    '{"success":false,"text":null,"preserved_meaning":null,"reason":"short reason"}. '
    "Never return moderation labels such as ABUSE, OK, REVIEW or POLITICAL."
)


def read_choice(response, payload):
    try:
        data = response.json()
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        usage = data.get("usage") or {}
        logger.info(
            "AI completion finish=%s output_tokens=%s reasoning_tokens=%s thinking=%s",
            finish,
            usage.get("completion_tokens"),
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            payload.get("thinking", {}).get("type", "provider_default"),
        )
        if finish in {"length", "content_filter", "tool_calls"}:
            raise AIRequestError("response_truncated" if finish == "length" else "provider_refusal")
        if choice["message"].get("refusal"):
            raise AIRequestError("provider_refusal")
        return choice["message"]["content"]
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise AIRequestError("invalid_output", detail="completion_envelope") from None


async def validated_completion(
    client,
    config,
    payload,
    limits,
    original,
    *,
    mode: str = "classification",
):
    if mode not in {"classification", "verification", "rewrite"}:
        raise ValueError(f"unsupported completion mode: {mode}")

    contract = {
        "classification": CLASSIFICATION,
        "verification": VERIFICATION,
        "rewrite": REWRITE,
    }[mode]

    for attempt in (1, 2):
        response = await post_completion(client, config, payload)
        try:
            raw = read_choice(response, payload)
            if mode == "verification":
                result = validate_verification(raw)
            elif mode == "rewrite":
                result = validate_rewrite_draft(raw, limits.max_input_chars)
            else:
                result = validate_output(raw, limits, original=original)

            if attempt == 2:
                runtime.metrics["format_recoveries"] += 1
                logger.info("AI response format recovered attempt=2/2 mode=%s", mode)

            if mode == "verification":
                logger.info(
                    "AI verification policy_pass=%s meaning_preserved=%s issues=%d",
                    result.policy_pass,
                    result.meaning_preserved,
                    len(result.issues),
                )
            elif mode == "rewrite":
                logger.info("AI rewrite success=%s", result.success)
            return result
        except AIProcessingError as exc:
            reason = getattr(exc, "reason", "invalid_output")
            if reason not in {"invalid_output", "invalid_verification", "invalid_rewrite"}:
                raise
            detail = getattr(exc, "detail", None) or "schema"
            logger.warning(
                "AI response rejected reason=%s detail=%s attempt=%d/2 mode=%s",
                reason,
                detail,
                attempt,
                mode,
            )
            if attempt == 2:
                raise
            runtime.metrics["format_retries"] += 1
            instruction = (
                "Previous response could not be validated (" + detail + "). "
                "Re-evaluate the original task and return a valid response. "
                "Do not relax the policy or invent facts. " + contract
            )
            payload = dict(
                payload,
                messages=[*payload["messages"], {"role": "system", "content": instruction}],
            )
