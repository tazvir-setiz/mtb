"""Bounded, request-local routing. No provider or model-name heuristics."""

from contextvars import ContextVar
from dataclasses import dataclass

fallback_attempt = ContextVar("fallback_attempt", default=False)

RECOVERABLE = frozenset({
    "timeout", "provider_error", "connection_error", "invalid_output",
    "invalid_meaning", "invalid_rewrite", "invalid_policy_verdict",
    "invalid_meaning_verdict", "response_truncated",
})


@dataclass
class ModelRouter:
    primary: str
    fallback: str
    escalations: int = 0
    reason: str = ""

    def escalate(self, reason: str) -> str | None:
        if not self.fallback or self.fallback == self.primary or self.escalations >= 1:
            return None
        self.escalations += 1
        self.reason = reason
        return self.fallback
