import asyncio
import logging
from urllib.parse import urlsplit

import httpx

from app.services.ai_policy import AIProcessingError

logger = logging.getLogger(__name__)


def model_options(config, mode: str | None = None):
    host = urlsplit(config.base_url).hostname
    is_supported_host = host in {"api.avalai.ir", "api.deepseek.com", "api.gapgpt.app"} or (
        bool(host) and any(d in host for d in ("avalai", "gapgpt", "deepseek"))
    )
    model_lower = config.model.lower()

    if getattr(config, "thinking_disabled", False):
        if is_supported_host or "deepseek" in model_lower or "luna" in model_lower:
            return {"thinking": {"type": "disabled"}}
        if any(m in model_lower for m in ("o1", "o3")):
            return {"reasoning_effort": "low"}
        return {"thinking": {"type": "disabled"}}

    if is_supported_host and (
        model_lower.startswith(("deepseek-v4", "deepseek-flash"))
        or "-luna" in model_lower
        or model_lower.endswith("-luna")
    ):
        return {"thinking": {"type": "disabled"}}

    return {}


class AIRequestError(AIProcessingError):
    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


async def post_completion(client, config, payload):
    from app.services.guard.budget import active_budget
    from app.services.model_routing import fallback_attempt

    attempts = 1 if fallback_attempt.get() else 2
    for attempt in range(1, attempts + 1):
        budget = active_budget.get()
        if budget:
            budget.request()
        try:
            response = await client.post(
                config.base_url, json=payload, headers={"Authorization": f"Bearer {config.api_key}"}
            )
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if attempt == attempts or (
                status is not None and status not in {408, 429, 500, 502, 503, 504}
            ):
                raise
            logger.warning(
                "AI transient failure type=%s status=%s retry=1 remaining_budget=shared",
                type(exc).__name__,
                status,
            )
            await asyncio.sleep(1)
