from dataclasses import dataclass, field
from enum import Enum


class Label(str, Enum):
    INJECTION = "INJECTION"
    SPAM = "SPAM"
    POLITICAL = "POLITICAL"
    PORN = "PORN"
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

    @property
    def action(self) -> str:
        if self.label in {Label.INJECTION, Label.SPAM, Label.PORN}:
            return "DROP"
        if self.label in {Label.POLITICAL, Label.REVIEW}:
            return "REVIEW"
        return "PUBLISH"
