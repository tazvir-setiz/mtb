from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.guard_config import GuardSettings
from app.services import ai_service, moderation_service
from app.services.ai_settings import save_ai_value
from app.services.ai_transport import AIRequestError
from app.services.guard.contracts import Verification
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime

ORIGINAL = "کیا یه غذای کیری میخوان"
REWRITTEN = "کیا یه غذای بی‌کیفیت می‌خوان؟"


def decision(label, text=None):
    return ModerationResult(label, 0.95, text, "AI")


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-key")
    classify = AsyncMock()
    verify = AsyncMock(return_value=Verification(True, True))
    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "verify", verify)
    return classify, verify


@pytest.mark.asyncio
@pytest.mark.parametrize("draft", [False, True])
async def test_two_false_abuse_decisions_still_get_verified_rewrite(model, draft):
    classify, verify = model
    classify.side_effect = [
        decision(Label.ABUSE),
        decision(Label.ABUSE),
        decision(Label.REWRITE, REWRITTEN),
    ]
    result = await moderation_service.moderate(1, 156, ORIGINAL, draft=draft)
    assert result.action == "PUBLISH"
    assert result.text == REWRITTEN
    assert classify.call_args.kwargs["salvage_abuse"]
    assert classify.call_args.args[0] == ORIGINAL
    assert verify.call_args.kwargs["verify_original"] == ORIGINAL
    assert verify.call_args.args[0] == REWRITTEN
    assert runtime.metrics["abuse_rewrite_attempts"] == 1


@pytest.mark.asyncio
async def test_rewrite_cannot_reverse_negative_quality(model):
    classify, verify = model
    classify.side_effect = [
        decision(Label.ABUSE),
        decision(Label.ABUSE),
        decision(Label.REWRITE, "کیا یه غذای خوب می‌خوان؟"),
    ]
    verify.return_value = Verification(
        True, False, ("negative quality changed to positive",), False
    )
    result = await moderation_service.moderate(1, 156, ORIGINAL)
    assert result.action == "REVIEW"
    assert result.reason == "meaning_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [Label.OK, Label.SANITIZE, Label.SPAM])
async def test_rescue_cannot_publish_unedited_original_or_new_unaudited_drop(model, label):
    classify, verify = model
    classify.side_effect = [decision(Label.ABUSE), decision(Label.ABUSE), decision(label)]
    assert (await moderation_service.moderate(1, 156, ORIGINAL)).action == "REVIEW"
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_substance_still_drops_and_never_loops(model):
    classify, verify = model
    classify.return_value = decision(Label.ABUSE)
    assert (await moderation_service.moderate(1, 156, ORIGINAL)).action == "DROP"
    assert classify.await_count == 3
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_failure_does_not_fall_back_to_drop(model):
    classify, _ = model
    classify.side_effect = [decision(Label.ABUSE), decision(Label.ABUSE), AIRequestError("timeout")]
    result = await moderation_service.moderate(1, 156, ORIGINAL)
    assert result.action == "REVIEW"
    assert result.reason == "timeout"


@pytest.mark.asyncio
async def test_rewrite_attempt_uses_existing_stage_budget(model, monkeypatch):
    classify, verify = model
    classify.return_value = decision(Label.ABUSE)
    monkeypatch.setattr(
        moderation_service, "guard_settings", replace(GuardSettings(), max_stages=2)
    )
    result = await moderation_service.moderate(1, 156, ORIGINAL)
    assert result.action == "REVIEW"
    assert result.reason == "budget_exhausted"
    assert classify.await_count == 2
    verify.assert_not_awaited()


@pytest.mark.asyncio
async def test_other_drop_categories_do_not_get_abuse_rescue(model):
    classify, _ = model
    classify.return_value = decision(Label.SPAM)
    assert (await moderation_service.moderate(1, 156, ORIGINAL)).action == "DROP"
    assert classify.await_count == 2


@pytest.mark.asyncio
async def test_transport_receives_dedicated_rewrite_task(monkeypatch):
    import json

    import httpx

    from app.services.ai_settings import AISettings

    manager = AsyncMock()
    manager.__aenter__.return_value.post.return_value = httpx.Response(
        200,
        request=httpx.Request("POST", "https://example.test"),
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {"label": "REWRITE", "confidence": 0.95, "text": REWRITTEN}
                        )
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: manager)
    result = await ai_service.classify(
        ORIGINAL,
        {},
        (),
        AISettings(True, "test", "https://example.test", "test"),
        GuardSettings(),
        rewrite=True,
        salvage_abuse=True,
    )
    assert result.text == REWRITTEN
    system = manager.__aenter__.return_value.post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "ABUSE REWRITE TASK" in system
    assert "do not turn bad into good" in system
