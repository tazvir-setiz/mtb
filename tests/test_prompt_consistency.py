from unittest.mock import AsyncMock

import pytest

from app.guard_config import GuardSettings
from app.services import ai_service
from app.services.ai_settings import AISettings
from app.services.guard_models import Label, ModerationResult


@pytest.mark.asyncio
async def test_classifier_political_examples_match_viewpoint_neutral_policy(monkeypatch):
    request = AsyncMock(return_value=ModerationResult(Label.OK, 1))
    monkeypatch.setattr(ai_service, "_request", request)
    config = AISettings(True, "key", "https://example.test", "model")
    await ai_service.classify("neutral report", {}, (), config, GuardSettings())
    system = request.call_args.args[0]["messages"][0]["content"]

    assert '"من با سیاست آمریکا مخالفم" -> POLITICAL' in system
    assert '"من با سیاست جمهوری اسلامی مخالفم" -> POLITICAL' in system
    assert '"در خبر درباره حماس صحبت شد" -> OK' in system
    assert "POLITICAL when the ORIGINAL message itself explicitly advocates" in system
    assert '"من با سیاست آمریکا مخالفم"\n-> OK' not in system
    assert '"من با سیاست جمهوری اسلامی مخالفم"\n-> OK' not in system
