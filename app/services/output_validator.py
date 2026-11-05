from dataclasses import replace
import math

from app.guard_config import GuardSettings
from app.services.guard_models import Label, ModerationResult
from app.services.response_format import OutputFormatError, response_object
from app.services.response_format import unique_fields as unique_fields


def _fuzzy_contains(original: str, quote: str) -> bool:
    if quote in original:
        return True
    def norm(s: str) -> str:
        s = s.replace("\u200c", "").replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
        return "".join(s.split()).lower()
    return norm(quote) in norm(original)


def validate_output(
    raw: str, limits: GuardSettings, *, original: str | None = None
) -> ModerationResult:
    detail = "schema"
    try:
        data = response_object(raw, limits.max_input_chars * 2 + 3000)
        allowed = {
            "label",
            "confidence",
            "text",
            "context_update",
            "violations",
            "has_substance",
            "ambiguities",
            "grounding_query",
            "action",
            "reason",
            "topic",
            "rewritten_text",
        }
        if set(data) - allowed:
            detail = "unknown_fields"
            raise ValueError()

        detail = "label"
        raw_label = data.get("label")
        raw_action = data.get("action")
        if not raw_label and raw_action:
            if raw_action == "SEND":
                raw_label = "OK"
            elif raw_action == "REWRITE":
                raw_label = "REWRITE"
            elif raw_action == "DROP":
                raw_label = "ABUSE"
            elif raw_action == "REVIEW":
                raw_label = "REVIEW"

        label = Label(raw_label)
        confidence = data.get("confidence", 0.95)
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            detail = "confidence"
            raise ValueError()

        # Classification and rewriting separation in legacy mode
        rewritten = data.get("rewritten_text")
        text_val = data.get("text")
        if text_val is not None and not rewritten and not raw_action:
            detail = "classification_text"
            raise ValueError()

        final_text = rewritten if rewritten is not None else text_val

        substance = data.get("has_substance")
        query = data.get("grounding_query")
        if query is not None and (not isinstance(query, str) or not query.strip() or len(query) > 120):
            detail = "grounding_query"
            raise ValueError()
        if substance is not None and type(substance) is not bool:
            detail = "has_substance"
            raise ValueError()

        ambiguities = data.get("ambiguities") if data.get("ambiguities") is not None else []
        if (
            not isinstance(ambiguities, list)
            or len(ambiguities) > 8
            or any(not isinstance(x, str) or not x.strip() or len(x) > 300 for x in ambiguities)
        ):
            detail = "ambiguities"
            raise ValueError()

        violations = data.get("violations") if data.get("violations") is not None else []
        if not isinstance(violations, list) or len(violations) > 8:
            detail = "violations"
            raise ValueError()
        detail = "violations"
        evidence = []
        for item in violations:
            if not isinstance(item, dict) or set(item) != {"rule_id", "evidence"}:
                raise ValueError()
            rule, quote = item["rule_id"], item["evidence"]
            if not isinstance(rule, str) or not isinstance(quote, str) or not quote.strip():
                raise ValueError()
            if original is not None and not _fuzzy_contains(original, quote) and rule != "off_topic":
                raise ValueError()
            evidence.append((rule, quote))

        update = data.get("context_update") if data.get("context_update") is not None else {}
        if not isinstance(update, dict) or set(update) - {
            "political",
            "topics_add",
            "entities_add",
            "aliases_add",
        }:
            detail = "context_update"
            raise ValueError()

    except OutputFormatError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise OutputFormatError(detail) from None

    threshold = (
        limits.ai_confidence_threshold
        if label in {Label.OK, Label.SANITIZE, Label.REWRITE}
        else limits.confidence_threshold
    )
    if confidence < threshold and label != Label.REWRITE:
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="low_confidence",
                                grounding_query=query)

    custom_reason = data.get("reason")
    result = ModerationResult(
        label=label,
        confidence=confidence,
        text=final_text if label == Label.REWRITE else None,
        source="AI",
        context_update=update,
        violations=tuple(evidence),
        has_substance=substance,
        ambiguities=tuple(ambiguities),
        grounding_query=query,
        reason=custom_reason,
    )

    is_off_topic = any(rule == "off_topic" for rule, _ in evidence) or "off_topic" in ambiguities
    if (
        original is not None
        and result.action == "DROP"
        and not is_off_topic
        and not custom_reason
        and (not evidence or (label == Label.ABUSE and substance is not False))
    ):
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="missing_evidence")

    if is_off_topic:
        result = replace(result, reason="off_topic")
    elif label == Label.REVIEW and not result.reason:
        if ambiguities:
            result = replace(result, reason=ambiguities[0])
        elif evidence:
            result = replace(result, reason=evidence[0][0])
    return result
