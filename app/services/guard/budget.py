import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from app.services.ai_policy import AIProcessingError


class BudgetExceeded(AIProcessingError):
    reason = "budget_exhausted"


@dataclass
class Budget:
    seconds: float
    max_stages: int
    max_requests: int
    started: float = field(default_factory=time.monotonic)
    stages: int = 0
    requests: int = 0

    def remaining(self):
        value = self.seconds - (time.monotonic() - self.started)
        if value <= 0:
            raise BudgetExceeded("budget_exhausted")
        return value

    def stage(self):
        self.remaining()
        if self.stages >= self.max_stages:
            raise BudgetExceeded("budget_exhausted")
        self.stages += 1

    def request(self):
        self.remaining()
        if self.requests >= self.max_requests:
            raise BudgetExceeded("budget_exhausted")
        self.requests += 1


active_budget = ContextVar("guard_budget", default=None)
