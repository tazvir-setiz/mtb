import time
from collections import Counter, OrderedDict

from app.services.guard_models import ModerationResult


class GuardRuntime:
    def __init__(self):
        self.metrics = Counter()
        self.cache: OrderedDict[str, tuple[float, ModerationResult]] = OrderedDict()
        self.failures: OrderedDict[str, tuple[int, float]] = OrderedDict()

    def cached(self, key: str) -> ModerationResult | None:
        item = self.cache.get(key)
        if item and item[0] > time.monotonic():
            self.cache.move_to_end(key)
            return item[1]
        self.cache.pop(key, None)
        return None

    def remember(self, key: str, result: ModerationResult, ttl: float, maximum: int) -> None:
        self.cache[key] = (time.monotonic() + ttl, result)
        self.cache.move_to_end(key)
        while len(self.cache) > maximum:
            self.cache.popitem(last=False)

    def unavailable(self, provider: str) -> bool:
        return self.failures.get(provider, (0, 0))[1] > time.monotonic()

    def failed(self, provider: str, limit: int, cooldown: float) -> None:
        count = self.failures.get(provider, (0, 0))[0] + 1
        self.failures[provider] = (count, time.monotonic() + cooldown if count >= limit else 0)
        self.failures.move_to_end(provider)
        while len(self.failures) > 16:
            self.failures.popitem(last=False)

    def snapshot(self) -> dict:
        total = self.metrics["total_messages"]
        return dict(self.metrics, ai_call_ratio=self.metrics["ai_calls"] / total if total else 0)


runtime = GuardRuntime()
