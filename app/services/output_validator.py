import json
import math
import re

from app.guard_config import GuardSettings
from app.services.ai_policy import AIProcessingError
from app.services.guard_models import Label, ModerationResult


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def validate_output(raw: str, limits: GuardSettings) -> ModerationResult:
    try:
        if not isinstance(raw, str) or len(raw) > limits.max_input_chars * 2 + 2000:
            raise ValueError()
        fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", raw, re.S)
        data = json.loads(fenced.group(1) if fenced else raw, object_pairs_hook=unique_fields)
        if not isinstance(data, dict) or set(data) - {
            "label",
            "confidence",
            "text",
            "context_update",
        }:
            raise ValueError()
        label = Label(data["label"])
        confidence = data["confidence"]
        if (
            type(confidence) not in (int, float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError()
        text = data.get("text")
        if text is not None and (not isinstance(text, str) or len(text) > limits.max_input_chars):
            raise ValueError()
        if label == Label.REWRITE and (not text or not text.strip() or "```" in text):
            raise ValueError()
        update = data.get("context_update", {})
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
    except (ValueError, TypeError, KeyError, RecursionError):
        raise AIProcessingError("Invalid structured guard response") from None
    threshold = (
        limits.ai_confidence_threshold
        if label in {Label.OK, Label.SANITIZE, Label.REWRITE}
        else limits.confidence_threshold
    )
    if confidence < threshold:
        return ModerationResult(Label.REVIEW, confidence, source="AI", reason="low_confidence")
    return ModerationResult(label, confidence, text, "AI", update)
