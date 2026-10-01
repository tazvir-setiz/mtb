import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.guard_config import GuardSettings
from app.services.ai_response import validated_completion
from app.services.ai_settings import AISettings
from app.services.ai_transport import AIRequestError
from app.services.guard.budget import Budget, BudgetExceeded, active_budget
from app.services.guard.contracts import validate_meaning_verdict
from app.services.guard_models import Label
from app.services.output_validator import validate_output
from app.services.response_format import OutputFormatError

CONFIG = AISettings(True, "secret-key", "https://example.test/v1/chat/completions", "test")
PAYLOAD = {"messages": [{"role": "user", "content": "private original"}]}
GOOD = {"label": "REWRITE", "confidence": 0.99, "text": None}


def response(content, finish="stop"):
    return httpx.Response(
        200,
        request=httpx.Request("POST", CONFIG.base_url),
        json={"choices": [{"finish_reason": finish, "message": {"content": content}}]},
    )


@pytest.mark.parametrize("optional", ["context_update", "violations", "ambiguities"])
def test_optional_null_is_empty_not_failure(optional):
    result = validate_output(json.dumps(dict(GOOD, **{optional: None})), GuardSettings())
    assert result.label == Label.REWRITE


@pytest.mark.parametrize(
    "field,value,detail",
    [
        ("confidence", "0.9", "confidence"),
        ("text", "unexpected rewrite", "classification_text"),
        ("label", "EDIT", "label"),
        ("context_update", [], "context_update"),
        ("violations", ["ABUSE"], "violations"),
        ("unexpected", 1, "unknown_fields"),
    ],
)
def test_schema_error_identifies_field(field, value, detail):
    with pytest.raises(OutputFormatError) as error:
        validate_output(json.dumps(dict(GOOD, **{field: value})), GuardSettings())
    assert error.value.detail == detail


def test_null_evidence_cannot_approve_drop():
    result = validate_output(
        '{"label":"ABUSE","confidence":1,"has_substance":false,"violations":null}',
        GuardSettings(),
        original="sample",
    )
    assert result.action == "REVIEW"
    assert result.reason == "missing_evidence"


def test_fenced_verification_is_valid_but_text_boolean_is_not():
    good = '{"passed":true,"issues":[],"repairable":false}'
    assert validate_meaning_verdict("```json\n" + good + "\n```").passed
    with pytest.raises(AIRequestError):
        validate_meaning_verdict(good.replace("true", '"true"'))


@pytest.mark.asyncio
async def test_invalid_format_retries_once_without_leaking_content(caplog, capsys):
    client = SimpleNamespace(
        post=AsyncMock(
            side_effect=[response("private malformed answer"), response(json.dumps(GOOD))]
        )
    )
    result = await validated_completion(
        client, CONFIG, PAYLOAD, GuardSettings(), "private original", mode="classification"
    )
    assert result.label == Label.REWRITE
    assert client.post.await_count == 2
    assert "invalid_json" in caplog.text
    assert "private malformed answer" not in caplog.text
    assert "secret-key" not in caplog.text
    captured = capsys.readouterr()
    assert "private malformed answer" not in captured.out
    assert "secret-key" not in captured.out
    retry = client.post.call_args.kwargs["json"]
    assert retry["messages"][-1]["role"] == "system"
    assert len(PAYLOAD["messages"]) == 1


@pytest.mark.asyncio
async def test_persistent_invalid_output_never_returns_original():
    client = SimpleNamespace(post=AsyncMock(return_value=response("not json")))
    with pytest.raises(OutputFormatError):
        await validated_completion(
            client, CONFIG, PAYLOAD, GuardSettings(), "original", mode="classification"
        )
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_format_retry_respects_shared_request_budget():
    client = SimpleNamespace(post=AsyncMock(return_value=response("not json")))
    token = active_budget.set(Budget(60, 6, 1))
    try:
        with pytest.raises(BudgetExceeded):
            await validated_completion(
                client, CONFIG, PAYLOAD, GuardSettings(), "original", mode="classification"
            )
    finally:
        active_budget.reset(token)
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_retry_still_checks_semantics():
    verdict = {
        "passed": False,
        "issues": ["reversed claim"],
        "repairable": False,
    }
    client = SimpleNamespace(
        post=AsyncMock(side_effect=[response("bad json"), response(json.dumps(verdict))])
    )
    result = await validated_completion(
        client, CONFIG, PAYLOAD, GuardSettings(), "original", mode="meaning_judge"
    )
    assert not result.passed


@pytest.mark.asyncio
async def test_refusal_not_retried_as_format_error():
    client = SimpleNamespace(post=AsyncMock(return_value=response("", "content_filter")))
    with pytest.raises(AIRequestError) as error:
        await validated_completion(
            client, CONFIG, PAYLOAD, GuardSettings(), "original", mode="classification"
        )
    assert error.value.reason == "provider_refusal"
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_repaired_response_still_passes_independent_verification(monkeypatch):
    from app.services import ai_service
    from app.services.ai_settings import save_ai_value
    from app.services.moderation_service import moderate

    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-key")
    manager = AsyncMock()
    post = manager.__aenter__.return_value.post
    post.side_effect = [
        response("invalid"),
        response(json.dumps(GOOD)),
        response(
            json.dumps(
                {
                    "protected_meaning": ["bad food"],
                    "removable_meaning": ["insult"],
                    "entities_relations": [],
                    "ambiguities": [],
                }
            )
        ),
        response(json.dumps({"success": True, "text": "کیا یه غذای بد می‌خوان؟", "reason": None})),
        response(json.dumps({"passed": True, "issues": [], "repairable": False})),
        response(json.dumps({"passed": True, "issues": [], "repairable": False})),
    ]
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: manager)
    monkeypatch.setattr(
        "app.services.guard.pipeline.search_latest_news", AsyncMock(return_value=[])
    )
    result = await moderate(1, 149, "کیا یه غذای کیری میخوان")
    assert result.action == "PUBLISH"
    assert result.text == "کیا یه غذای بد می‌خوان؟"
    assert post.await_count == 6
    verification_input = json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])
    assert verification_input["original"] == "کیا یه غذای کیری میخوان"
    assert verification_input["candidate"] == result.text


@pytest.mark.asyncio
async def test_format_retry_does_not_reset_request_timeout(monkeypatch):
    import asyncio
    from dataclasses import replace

    from app.services import ai_service

    manager = AsyncMock()
    attempts = 0

    async def delayed(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return response("invalid")
        await asyncio.sleep(1)
        return response(json.dumps(GOOD))

    manager.__aenter__.return_value.post.side_effect = delayed
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: manager)
    with pytest.raises(AIRequestError) as error:
        await ai_service.classify(
            "sample",
            {},
            (),
            CONFIG,
            replace(GuardSettings(), timeout_seconds=0.02),
            policy="test policy",
        )
    assert error.value.reason == "timeout"
    assert attempts == 2
