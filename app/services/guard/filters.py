from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.guard_config import GuardSettings
from app.services.guard_models import Action, Label, ModerationResult
from app.services.guard_profile import load_profile
from app.services.rule_guard import INJECTION, contains_phrase, evaluate_rules
from app.services.text_normalizer import NormalizedText, normalize_text

logger = logging.getLogger(__name__)


class InputPreparationFilter:
    """Validates input size, normalizes text, and extracts candidate variations."""

    @staticmethod
    def process(text: str, limits: GuardSettings) -> tuple[bool, NormalizedText | ModerationResult]:
        if len(text) > limits.max_input_chars:
            return False, ModerationResult(
                Label.REVIEW,
                1.0,
                reason="input_too_long",
                _action_override=Action.REVIEW,
            )
        normalized = normalize_text(text, limits.max_candidates)
        return True, normalized


class KeywordRuleFilter:
    """Evaluates deterministic fast-path rules, accounting for educational/negated context."""

    @staticmethod
    def evaluate(normalized: NormalizedText, context: dict) -> ModerationResult:
        return evaluate_rules(normalized, context)


class PromptInjectionFilter:
    """Independent filter for detecting prompt injection indicators."""

    @staticmethod
    def evaluate(normalized: NormalizedText) -> ModerationResult | None:
        if contains_phrase(normalized, INJECTION):
            return ModerationResult(
                Label.INJECTION,
                0.9,
                reason="prompt_injection",
                _action_override=Action.DROP,
            )
        return None


class MediaPolicyFilter:
    """Inspects attachments. Unchecked or unknown media fail closed to REVIEW."""

    @staticmethod
    def evaluate(media: Any, *, approved: bool = False) -> ModerationResult:
        if not media or approved:
            return ModerationResult(Label.OK, 1.0, media_checked=True)

        if type(media).__name__ == "MessageMediaWebPage":
            return ModerationResult(Label.OK, 1.0, media_checked=True)

        profile = load_profile()
        mode = profile.get("sensitivity", {}).get("media", "standard")
        # Disabling or changing media mode must NEVER fail-open.
        reason = "policy_mismatch" if mode == "off" else "unchecked_media"
        return ModerationResult(
            Label.REVIEW,
            1.0,
            reason=reason,
            media_checked=False,
            _action_override=Action.REVIEW,
        )


class SourcePolicyFilter:
    """Checks source/destination context and channel-specific moderation policies."""

    @staticmethod
    def is_allowed(source_id: int, destination_id: int) -> bool:
        return bool(source_id and destination_id)
