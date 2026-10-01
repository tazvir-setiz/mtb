import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.guard_config import GuardSettings
from app.services.ai_service import classify, generate_rewrite
from app.services.ai_settings import AISettings
from app.services.ai_transport import AIRequestError, model_options, post_completion
from app.services.guard.contracts import MeaningDecomposition

CONFIG = AISettings(
    True, "private-test-key", "https://api.avalai.ir/v1/chat/completions", "deepseek-v4.1-flash"
)


def test_thinking_override_is_scoped_to_supported_provider_and_model():
    assert model_options(CONFIG) == {"thinking": {"type": "disabled"}}
    assert model_options(replace(CONFIG, model="another-model")) == {}
    assert model_options(replace(CONFIG, base_url="https://unrelated.test/v1")) == {}


@pytest.mark.asyncio
async def test_provider_failure_is_retried_once_with_identical_payload(monkeypatch):
    monkeypatch.setattr("app.services.ai_transport.asyncio.sleep", AsyncMock())
    request = httpx.Request("POST", CONFIG.base_url)
    client = SimpleNamespace(
        post=AsyncMock(
            side_effect=[httpx.Response(503, request=request), httpx.Response(200, request=request)]
        )
    )
    result = await post_completion(client, CONFIG, {"text": "sample"})
    assert result.status_code == 200
    assert client.post.await_count == 2
    assert client.post.call_args_list[0] == client.post.call_args_list[1]


@pytest.mark.asyncio
async def test_invalid_credentials_are_not_retried():
    client = SimpleNamespace(
        post=AsyncMock(
            return_value=httpx.Response(401, request=httpx.Request("POST", CONFIG.base_url))
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        await post_completion(client, CONFIG, {})
    client.post.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish,reason", [("length", "response_truncated"), ("content_filter", "provider_refusal")]
)
async def test_reasoning_only_response_has_specific_failure(monkeypatch, finish, reason):
    response = httpx.Response(
        200,
        request=httpx.Request("POST", CONFIG.base_url),
        json={
            "choices": [
                {
                    "finish_reason": finish,
                    "message": {"content": "", "reasoning_content": "must not be published"},
                }
            ]
        },
    )
    manager = AsyncMock()
    manager.__aenter__.return_value.post.return_value = response
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", lambda **_: manager)
    with pytest.raises(AIRequestError) as error:
        await classify("sample", {}, (), CONFIG, GuardSettings())
    assert error.value.reason == reason


@pytest.mark.asyncio
@pytest.mark.parametrize("rewrite", [False, True])
async def test_rewrite_request_disables_thinking_and_keeps_output(monkeypatch, rewrite):
    result = (
        {"success": True, "text": "خیلی دوستت دارم.", "reason": None}
        if rewrite
        else {"label": "REWRITE", "confidence": 0.9, "text": None}
    )
    response = httpx.Response(
        200,
        request=httpx.Request("POST", CONFIG.base_url),
        json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]},
    )
    manager = AsyncMock()
    manager.__aenter__.return_value.post.return_value = response
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", lambda **_: manager)
    if rewrite:
        output = await generate_rewrite(
            "خیلی دوستت دارم مثل کیر",
            MeaningDecomposition(("affection",), ("insult",), ()),
            {},
            CONFIG,
            GuardSettings(),
        )
    else:
        output = await classify("خیلی دوستت دارم مثل کیر", {}, (), CONFIG, GuardSettings())
    assert output.text == result["text"]
    payload = manager.__aenter__.return_value.post.call_args.kwargs["json"]
    assert ("CLASSIFIER ONLY" in payload["messages"][0]["content"]) is (not rewrite)
    assert manager.__aenter__.return_value.post.call_args.kwargs["json"]["thinking"] == {
        "type": "disabled"
    }


@pytest.mark.asyncio
async def test_retry_still_obeys_total_deadline(monkeypatch):
    manager = AsyncMock()
    manager.__aenter__.return_value.post.side_effect = httpx.ConnectError("offline")
    monkeypatch.setattr("app.services.ai_service.httpx.AsyncClient", lambda **_: manager)
    with pytest.raises(AIRequestError) as error:
        await asyncio.wait_for(
            classify("sample", {}, (), CONFIG, replace(GuardSettings(), timeout_seconds=0.02)), 0.5
        )
    assert error.value.reason == "timeout"
