import asyncio
import json
import logging
import time

from app.guard_config import guard_settings
from app.services.ai_settings import load_ai_settings
from app.services.guard_runtime import runtime
from app.telegram import auto_forward

logger = logging.getLogger(__name__)


def log_status(client, started):
    ai = load_ai_settings()
    logger.info(
        "Status uptime=%.0fs telegram_connected=%s auto_enabled=%s auto=%s "
        "ai_enabled=%s ai_model=%s api_key_configured=%s ai_timeout=%.1fs guard=%s",
        time.monotonic() - started,
        client.is_connected(),
        auto_forward.is_enabled(),
        json.dumps(auto_forward.status_snapshot(), sort_keys=True),
        ai.enabled,
        ai.model,
        bool(ai.api_key),
        guard_settings.timeout_seconds,
        json.dumps(runtime.snapshot(), sort_keys=True),
    )


async def monitor_status(client):
    started = time.monotonic()
    while True:
        try:
            log_status(client, started)
        except Exception as exc:
            logger.error("Status report failed type=%s", type(exc).__name__)
        await asyncio.sleep(60)
