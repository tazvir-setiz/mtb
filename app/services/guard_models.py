from dataclasses import dataclass, field
from enum import Enum


class Action(str, Enum):
    PUBLISH = "PUBLISH"
    DROP = "DROP"
    REVIEW = "REVIEW"
    RETRY_PENDING = "RETRY_PENDING"


class Label(str, Enum):
    INJECTION = "INJECTION"
    SPAM = "SPAM"
    POLITICAL = "POLITICAL"
    PORN = "PORN"
    ABUSE = "ABUSE"
    HATE = "HATE"
    THREAT = "THREAT"
    REWRITE = "REWRITE"
    SANITIZE = "SANITIZE"
    OK = "OK"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class ModerationResult:
    label: Label
    confidence: float
    text: str | None = None
    source: str = "RULE"
    context_update: dict = field(default_factory=dict)
    reason: str = ""
    violations: tuple[tuple[str, str], ...] = ()
    has_substance: bool | None = None
    ambiguities: tuple[str, ...] = ()
    grounding_query: str | None = None
    media_checked: bool = False
    _action_override: Action | None = None

    @property
    def action(self) -> str:
        if self._action_override is not None:
            return self._action_override.value
        if self.label in {
            Label.INJECTION,
            Label.SPAM,
            Label.PORN,
            Label.ABUSE,
            Label.HATE,
            Label.THREAT,
        }:
            return Action.DROP.value
        if self.label in {Label.POLITICAL, Label.REVIEW}:
            return Action.REVIEW.value
        return Action.PUBLISH.value
