import math

from app.guard_config import GuardSettings
from app.services.guard_models import Label, ModerationResult
from app.services.response_format import OutputFormatError, response_object
from app.services.response_format import unique_fields as unique_fields


def validate_output(raw: str, limits: GuardSettings, *, original: str | None = None) -> ModerationResult:
    detail = "schema"
    try:
        data = response_object(raw, limits.max_input_chars * 2 + 3000)
        allowed = {
            "label", "confidence", "text", "context_update",
            "violations", "has_substance", "ambiguities",
        }
        if set(data) - allowed:
            detail = "unknown_fields"
            raise ValueError()

        label = Label(data["label"])
        confidence = data["confidence"]
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            detail = "confidence"
            raise ValueError()

        # Classification and rewriting are separated.
        if data.get("text") is not None:
            detail = "classification_text"
            raise ValueError()

        substance = data.get("has_substance")
        if substance is not None and type(substance) is not bool:
            detail = "has_substance"
            raise ValueError()

        ambiguities = data.get("ambiguities") or []
        if (
            not isinstance(ambiguities, list)
            or len(ambiguities) > 8
            or any(not isinstance(x, str) or not x.strip() or len(x) > 300 for x in ambiguities)
        ):
            detail = "ambiguities"
            raise ValueError()

        violations = data.get("violations") or []
        if not isinstance(violations, list) or len(violations) > 8:
            detail = "violations"
            raise ValueError()
        evidence = []
        for item in violations:
            if not isinstance(item, dict) or set(item) != {"rule_id", "evidence"}:
                raise ValueError()
            rule, quote = item["rule_id"], item["evidence"]
            if not isinstance(rule, str) or not isinstance(quote, str) or not quote.strip():
                raise ValueError()
            if original is not None and quote not in original:
                raise ValueError()
            evidence.append((rule, quote))

        update = data.get("context_update") or {}
        if not isinstance(update, dict) or set(update) - {
            "political", "topics_add", "entities_add", "aliases_add"
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
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="low_confidence")

    result = ModerationResult(
        label=label,
        confidence=confidence,
        text=None,
        source="AI",
        context_update=update,
        violations=tuple(evidence),
        has_substance=substance,
        ambiguities=tuple(ambiguities),
    )

    if (
        original is not None
        and result.action == "DROP"
        and (not evidence or (label == Label.ABUSE and substance is not False))
    ):
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="missing_evidence")
    return result
