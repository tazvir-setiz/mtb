import asyncio
import logging
from urllib.parse import urlsplit

import httpx

from app.services.ai_policy import AIProcessingError

logger = logging.getLogger(__name__)


def model_options(config):
    host = urlsplit(config.base_url).hostname
    if host in {"api.avalai.ir", "api.deepseek.com"} and config.model.lower().startswith(
        ("deepseek-v4", "deepseek-flash")
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

    for attempt in (1, 2):
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
            if attempt == 2 or (
                status is not None and status not in {408, 429, 500, 502, 503, 504}
            ):
                raise
            logger.warning(
                "AI transient failure type=%s status=%s retry=1 remaining_budget=shared",
                type(exc).__name__,
                status,
            )
            await asyncio.sleep(1)
