import math
from dataclasses import dataclass

from app.config import ConfigError, optional_env


@dataclass(frozen=True)
class GuardSettings:
    confidence_threshold: float = 0.85
    max_input_chars: int = 4000
    max_output_tokens: int = 200
    max_candidates: int = 8
    max_topics: int = 5
    max_entities: int = 8
    max_aliases: int = 8
    context_ttl_hours: float = 24
    cache_ttl_seconds: float = 600
    cache_size: int = 256
    timeout_seconds: float = 20
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
    if values["confidence_threshold"] > 1:
        raise ConfigError("AI_GUARD_CONFIDENCE_THRESHOLD must be at most 1")
    return GuardSettings(**values)


guard_settings = load_guard_settings()
