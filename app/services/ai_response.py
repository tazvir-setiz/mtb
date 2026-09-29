import logging

from app.services.ai_policy import AIProcessingError
from app.services.ai_transport import AIRequestError, post_completion
from app.services.guard.contracts import (
    validate_meaning,
    validate_meaning_verdict,
    validate_policy_verdict,
    validate_rewrite_draft,
)
from app.services.guard_runtime import runtime
from app.services.output_validator import validate_output

logger = logging.getLogger(__name__)

CONTRACTS = {
    "classification": (
    'Return exactly one JSON object with this schema: '
    '{"label":"OK|SANITIZE|REWRITE|REVIEW|POLITICAL|ABUSE|HATE|THREAT|SPAM|PORN|INJECTION",'
    '"confidence":0.0,'
    '"text":null,'
    '"has_substance":true,'
    '"ambiguities":[],'
    '"violations":[{"rule_id":"abuse","evidence":"exact quote from original message"}],'
    '"context_update":{}}. '
    'Every item in "violations" MUST be an object containing exactly "rule_id" and "evidence". '
    '"evidence" MUST be an exact substring copied from the original message. '
    'For no violation use "violations":[]. '
    'For ABUSE set "has_substance":false only when the insult/attack is essentially the whole meaning. '
    "The classifier never writes replacement prose."
    ),
    "meaning": (
        'Return exactly one JSON object with this schema: '
        '{"protected_meaning":["plain string"],'
        '"removable_meaning":["plain string"],'
        '"entities_relations":["plain string"],'
        '"ambiguities":["plain string"]}. '
        'EVERY item in EVERY array MUST be a plain JSON string. '
        'Do NOT put objects, dictionaries, key/value structures, arrays, or nested JSON inside any array. '
        'For entities_relations, describe each important relation as one short natural-language string, '
        'for example "گوینده برنامه را منفی ارزیابی می‌کند" or '
        '"ساعت شروع برنامه ۸ است". '
        'Use [] when an array has no items.'
    ),
    "rewrite": (
        'Return only {"success":true,"text":"full rewrite","reason":null}, or '
        '{"success":false,"text":null,"reason":"why no faithful rewrite exists"}.'
    ),
    "policy_judge": (
    'Return exactly one JSON object with this schema: '
    '{"passed":true,"issues":[],"repairable":false}. '
    '"passed" MUST be a boolean. '
    '"repairable" MUST be a boolean. '
    '"issues" MUST always be an array of strings. '
    'Each issue MUST be a plain string describing one policy problem. '
    'Never put objects, dictionaries, labels, evidence objects, or nested structures inside "issues". '
    'If there are no policy problems, return exactly '
    '{"passed":true,"issues":[],"repairable":false}. '
    'If there are policy problems, use for example '
    '{"passed":false,"issues":["Candidate still contains a direct personal insult."],"repairable":true}.'
    ),
    "meaning_judge": (
    'Return exactly one JSON object with this schema: '
    '{"passed":true,"issues":[],"repairable":false}. '
    '"passed" MUST be a boolean. '
    '"repairable" MUST be a boolean. '
    '"issues" MUST always be an array of strings. '
    'Each issue MUST be a plain string describing one meaning-preservation problem. '
    'Never put objects, dictionaries, labels, evidence objects, or nested structures inside "issues". '
    'If meaning is preserved, return exactly '
    '{"passed":true,"issues":[],"repairable":false}.'
),
}


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


def _validate(mode, raw, limits, original):
    if mode == "classification":
        return validate_output(raw, limits, original=original)
    if mode == "meaning":
        return validate_meaning(raw)
    if mode == "rewrite":
        return validate_rewrite_draft(raw, limits.max_input_chars)
    if mode == "policy_judge":
        return validate_policy_verdict(raw)
    if mode == "meaning_judge":
        return validate_meaning_verdict(raw)
    raise ValueError(mode)


async def validated_completion(client, config, payload, limits, original, *, mode):
    for attempt in (1, 2):
        response = await post_completion(client, config, payload)

        raw = read_choice(response, payload)

        print(f"\n=== AI RAW RESPONSE [{mode}] attempt={attempt} ===")
        print(raw)
        print("================================\n")

        try:
            result = _validate(mode, raw, limits, original)

            if attempt == 2:
                runtime.metrics["format_recoveries"] += 1

            return result

        except AIProcessingError as exc:
            reason = getattr(exc, "reason", "invalid_output")

            print(f"=== VALIDATION FAILED ===")
            print(f"mode: {mode}")
            print(f"attempt: {attempt}")
            print(f"reason: {reason}")
            print(f"detail: {getattr(exc, 'detail', None)}")
            print("=========================\n")

            if attempt == 2:
                raise

            runtime.metrics["format_retries"] += 1

            payload = dict(
                payload,
                messages=[
                    *payload["messages"],
                    {
                        "role": "system",
                        "content": (
                            "Your previous response failed validation. "
                            "Re-evaluate the same task. "
                            "Return ONLY the required JSON schema. "
                            + CONTRACTS[mode]
                        ),
                    },
                ],
            )