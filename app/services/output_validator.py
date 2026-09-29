import math

from app.guard_config import GuardSettings
from app.services.guard_models import Label, ModerationResult
from app.services.response_format import OutputFormatError, response_object
from app.services.response_format import unique_fields as unique_fields


def validate_output(
    raw: str, limits: GuardSettings, *, original: str | None = None
) -> ModerationResult:
    detail = "schema"
    try:
        data = response_object(raw, limits.max_input_chars * 2 + 2000)
        detail = "unknown_fields"
        if not isinstance(data, dict) or set(data) - {
            "label",
            "confidence",
            "text",
            "context_update",
            "violations",
            "has_substance",
            "ambiguities",
        }:
            raise ValueError()

        detail = "label"
        label = Label(data["label"])

        detail = "confidence"
        confidence = data["confidence"]
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError()

        # Classification and writing are deliberately separated. A classifier
        # may request REWRITE but may never provide the rewritten text.
        detail = "classification_text"
        text = data.get("text")
        if text is not None:
            raise ValueError()

        detail = "has_substance"
        substance = data.get("has_substance")
        if substance is not None and type(substance) is not bool:
            raise ValueError()

        detail = "ambiguities"
        ambiguities = data.get("ambiguities") if data.get("ambiguities") is not None else []
        if (
            not isinstance(ambiguities, list)
            or len(ambiguities) > 8
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 300
                for item in ambiguities
            )
        ):
            raise ValueError()

        detail = "violations"
        violations = data.get("violations") if data.get("violations") is not None else []
        if not isinstance(violations, list) or len(violations) > 8:
            raise ValueError()
        evidence = []
        for item in violations:
            if not isinstance(item, dict) or set(item) != {"rule_id", "evidence"}:
                raise ValueError()
            rule, quote = item["rule_id"], item["evidence"]
            if (
                not isinstance(rule, str)
                or not 0 < len(rule) <= 64
                or not isinstance(quote, str)
                or not 0 < len(quote.strip()) <= 500
            ):
                raise ValueError()
            if original is not None and quote not in original:
                raise ValueError()
            evidence.append((rule, quote))

        detail = "context_update"
        update = data.get("context_update") if data.get("context_update") is not None else {}
        if not isinstance(update, dict) or set(update) - {
            "political",
            "topics_add",
            "entities_add",
            "aliases_add",
        }:
            raise ValueError()
        if "political" in update and type(update["political"]) is not bool:
            raise ValueError()
        for name, maximum in (
            ("topics_add", limits.max_topics),
            ("entities_add", limits.max_entities),
        ):
            items = update.get(name, [])
            if (
                not isinstance(items, list)
                or len(items) > maximum
                or any(not isinstance(x, str) or len(x) > 48 for x in items)
            ):
                raise ValueError()
        aliases = update.get("aliases_add", {})
        if not isinstance(aliases, dict) or len(aliases) > limits.max_aliases:
            raise ValueError()
        if any(not isinstance(v, str) or len(k) > 48 or len(v) > 48 for k, v in aliases.items()):
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
    if confidence < threshold:
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="low_confidence")

    result = ModerationResult(
        label,
        confidence,
        None,
        "AI",
        update,
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
