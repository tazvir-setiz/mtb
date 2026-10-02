from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.guard_config import GuardSettings
from app.services import ai_service
from app.services.ai_response import validated_completion
from app.services.ai_settings import AISettings
from app.services.ai_transport import AIRequestError
from app.services.guard.budget import Budget, active_budget
from app.services.guard.pipeline import GuardPipeline
from app.services.guard_models import Label, ModerationResult
from app.services.model_routing import fallback_attempt
from app.services.response_format import OutputFormatError


def pipeline(**limits):
    return GuardPipeline(AISettings(True, "key", "https://example.test", "primary", "fallback"),
                         replace(GuardSettings(), **limits), {}, "policy")


@pytest.mark.asyncio
async def test_primary_success_and_low_confidence_escalation(monkeypatch):
    classify = AsyncMock(return_value=ModerationResult(Label.OK, .99))
    monkeypatch.setattr(ai_service, "classify", classify)
    assert (await pipeline().run("text")).action == "PUBLISH"
    assert classify.call_args.args[3].model == "primary"
    classify.reset_mock()
    classify.side_effect = [ModerationResult(Label.REVIEW, .4, reason="low_confidence"),
                            ModerationResult(Label.OK, .99)]
    guard = pipeline()
    assert (await guard.run("text")).action == "PUBLISH"
    assert [call.args[3].model for call in classify.call_args_list] == ["primary", "fallback"]
    assert guard.router.escalations == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,expected", [("timeout", 2), ("provider_error", 2),
    ("invalid_output", 2), ("invalid_credentials", 1), ("rate_limit", 1),
    ("circuit_open", 1), ("bad_request", 1)])
async def test_failure_policy(monkeypatch, reason, expected):
    classify = AsyncMock(side_effect=AIRequestError(reason))
    monkeypatch.setattr(ai_service, "classify", classify)
    guard = pipeline()
    result = await guard.run("text")
    assert result.action == "REVIEW"
    assert classify.await_count == expected
    assert guard.router.escalations <= 1


@pytest.mark.asyncio
async def test_stage_budget_prevents_fallback(monkeypatch):
    classify = AsyncMock(return_value=ModerationResult(Label.REVIEW, .4))
    monkeypatch.setattr(ai_service, "classify", classify)
    result = await pipeline(max_stages=1).run("text")
    assert result.reason == "budget_exhausted"
    assert classify.await_count == 1


@pytest.mark.asyncio
async def test_fallback_has_one_physical_request_and_validates_schema():
    response = httpx.Response(200, request=httpx.Request("POST", "https://example.test"),
        json={"choices": [{"message": {"content": '{"label":"nonsense"}'}}]})
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    budget = Budget(10, 12, 12)
    bt = active_budget.set(budget)
    ft = fallback_attempt.set(True)
    try:
        with pytest.raises(OutputFormatError) as error:
            await validated_completion(client, pipeline().config,
                {"messages": []}, GuardSettings(), "text", mode="classification")
        assert error.value.reason == "invalid_output"
        assert client.post.await_count == budget.requests == 1
    finally:
        fallback_attempt.reset(ft)
        active_budget.reset(bt)
