import math
from dataclasses import dataclass

from app.config import ConfigError, optional_env


@dataclass(frozen=True)
class GuardSettings:
    confidence_threshold: float = 0.85
    ai_confidence_threshold: float = 0.75
    max_input_chars: int = 4000
    max_output_tokens: int = 1024
    max_candidates: int = 8
    max_topics: int = 5
    max_entities: int = 8
    max_aliases: int = 8
    context_ttl_hours: float = 24
    cache_ttl_seconds: float = 600
    cache_size: int = 256
    timeout_seconds: float = 60
    total_timeout_seconds: float = 120
    max_stages: int = 6
    max_requests: int = 8
    failure_limit: int = 2
    cooldown_seconds: float = 60


def load_guard_settings() -> GuardSettings:
    defaults = GuardSettings()
    values = {}
    for name, default in vars(defaults).items():
        value = type(default)(optional_env(f"AI_GUARD_{name.upper()}", str(default)))
        if not math.isfinite(value) or value <= 0:
            raise ConfigError(f"Invalid AI_GUARD_{name.upper()}")
        values[name] = value
    for name in ("confidence_threshold", "ai_confidence_threshold"):
        if values[name] > 1:
            raise ConfigError(f"AI_GUARD_{name.upper()} must be at most 1")
    return GuardSettings(**values)


guard_settings = load_guard_settings()
