import asyncio
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.guard_config import GuardSettings
from app.services import ai_service, moderation_service
from app.services.ai_settings import AISettings, save_ai_value
from app.services.ai_transport import AIRequestError, post_completion
from app.services.guard.budget import Budget, BudgetExceeded, active_budget
from app.services.guard.contracts import Verification, validate_verification
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime
from app.services.output_validator import validate_output
from app.services.review_rewriter import rewrite_draft


def decision(label, text=None):
    return ModerationResult(label, 0.99, text, "AI")


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test")
    classify = AsyncMock(return_value=decision(Label.OK))
    verify = AsyncMock(return_value=Verification(True, True))
    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "verify", verify)
    return classify, verify


@pytest.mark.asyncio
async def test_negated_ad_goes_to_ai_instead_of_local_drop(model):
    result = await moderation_service.moderate(1, 1, "ما خرید فیلترشکن نداریم")
    assert result.action == "PUBLISH"
    model[0].assert_awaited_once()
    model[1].assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_policy_cannot_be_bypassed_by_greeting(model, monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "settings",
        replace(ai_service.settings, ai_guardrails="Do not publish greetings."),
    )
    model[0].return_value = decision(Label.REVIEW)
    result = await moderation_service.moderate(1, 1, "سلام")
    assert result.action == "REVIEW"
    assert "Do not publish greetings." in model[0].call_args.kwargs["policy"]


@pytest.mark.asyncio
async def test_reversed_negation_is_rejected(model):
    model[0].return_value = decision(Label.REWRITE, "جلسه لغو شد")
    model[1].return_value = Verification(True, False, ("negation reversed",), False)
    result = await moderation_service.moderate(1, 1, "جلسه لغو نشد")
    assert result.action == "REVIEW"
    assert result.reason == "meaning_changed"
    assert model[1].call_args.kwargs["verify_original"] == "جلسه لغو نشد"
    assert model[1].call_args.args[0] == "جلسه لغو شد"


@pytest.mark.asyncio
async def test_one_targeted_repair_receives_issues_and_original(model):
    model[0].side_effect = [
        decision(Label.REWRITE, "جلسه لغو شد"),
        decision(Label.REWRITE, "جلسه لغو نشده است"),
    ]
    model[1].side_effect = [
        Verification(True, False, ("negation reversed",), True),
        Verification(True, True),
    ]
    result = await moderation_service.moderate(1, 1, "جلسه لغو نشد")
    assert result.text == "جلسه لغو نشده است"
    assert model[0].call_args.args[0] == "جلسه لغو نشد"
    assert model[0].call_args.kwargs["feedback"] == ("negation reversed",)
    assert model[1].await_count == 2


@pytest.mark.asyncio
async def test_repair_loop_is_bounded(model):
    model[0].return_value = decision(Label.REWRITE, "bad candidate")
    model[1].return_value = Verification(False, False, ("invented facts",), True)
    result = await moderation_service.moderate(1, 1, "original text")
    assert result.action == "REVIEW"
    assert model[0].await_count == model[1].await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [Label.SPAM, Label.PORN, Label.INJECTION, Label.ABUSE])
async def test_all_model_drops_require_audit(model, label):
    model[0].return_value = decision(label)
    assert (await moderation_service.moderate(1, 1, "unknown message")).action == "DROP"
    assert model[0].await_count == 2
    assert model[0].call_args.kwargs["audit_abuse"]
    model[1].assert_not_awaited()


@pytest.mark.asyncio
async def test_conflicting_drop_labels_are_not_silent_drop(model):
    model[0].side_effect = [decision(Label.SPAM), decision(Label.PORN)]
    result = await moderation_service.moderate(1, 1, "unknown message")
    assert result.reason == "conflicting_decisions"


@pytest.mark.asyncio
async def test_pipeline_stage_budget_stops_before_publication(model, monkeypatch):
    monkeypatch.setattr(
        moderation_service, "guard_settings", replace(GuardSettings(), max_stages=1)
    )
    result = await moderation_service.moderate(1, 1, "unknown message")
    assert result.action == "REVIEW"
    assert result.reason == "budget_exhausted"
    model[1].assert_not_awaited()
    assert active_budget.get() is None


@pytest.mark.asyncio
async def test_total_deadline_is_shared_across_stages(model, monkeypatch):
    async def analyze(*args, **kwargs):
        await asyncio.sleep(0.04)
        return decision(Label.OK)

    async def verify(*args, **kwargs):
        await asyncio.sleep(0.04)
        return Verification(True, True)

    model[0].side_effect = analyze
    model[1].side_effect = verify
    monkeypatch.setattr(
        moderation_service, "guard_settings", replace(GuardSettings(), total_timeout_seconds=0.06)
    )
    result = await moderation_service.moderate(1, 1, "unknown message")
    assert result.action == "REVIEW"
    assert result.reason == "budget_exhausted"


@pytest.mark.asyncio
async def test_manual_rewrite_uses_same_circuit_and_metrics(model):
    model[0].side_effect = AIRequestError("timeout")
    for _ in range(3):
        with pytest.raises(AIRequestError):
            await rewrite_draft("unknown text")
    assert model[0].await_count == 2
    assert runtime.metrics["ai_calls"] == 2
    assert runtime.metrics["circuit_skips"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"policy_pass": "true", "meaning_preserved": True, "issues": [], "repairable": False},
        {
            "policy_pass": True,
            "meaning_preserved": True,
            "issues": ["contradiction"],
            "repairable": False,
        },
        {"policy_pass": False, "meaning_preserved": True, "issues": [], "repairable": True},
    ],
)
def test_invalid_or_contradictory_verification_fails_closed(payload):
    with pytest.raises(AIRequestError):
        validate_verification(json.dumps(payload))


@pytest.mark.asyncio
async def test_http_verifier_receives_original_and_candidate(monkeypatch):
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://example.test"),
        json={
            "choices": [
                {
                    "message": {
                        "content": '{"policy_pass":true,"meaning_preserved":true,"issues":[],"repairable":false}'
                    }
                }
            ]
        },
    )
    manager = AsyncMock()
    manager.__aenter__.return_value.post.return_value = response
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kw: manager)
    result = await ai_service.verify(
        "candidate",
        {},
        (),
        AISettings(True, "test", "https://example.test", "test"),
        GuardSettings(),
        verify_original="original",
    )
    assert result.passed
    body = manager.__aenter__.return_value.post.call_args.kwargs["json"]
    data = json.loads(body["messages"][1]["content"])
    assert data["original"] == "original" and data["candidate"] == "candidate"
    assert "VERIFICATION TASK" in body["messages"][0]["content"]


@pytest.mark.asyncio
async def test_network_retry_consumes_shared_request_budget(monkeypatch):
    from types import SimpleNamespace

    client = SimpleNamespace(post=AsyncMock(side_effect=httpx.ConnectError("offline")))
    monkeypatch.setattr("app.services.ai_transport.asyncio.sleep", AsyncMock())
    budget = Budget(120, 6, 1)
    token = active_budget.set(budget)
    try:
        with pytest.raises(BudgetExceeded):
            await post_completion(
                client, AISettings(True, "test", "https://example.test", "test"), {}
            )
        client.post.assert_awaited_once()
    finally:
        active_budget.reset(token)


@pytest.mark.parametrize(
    "payload",
    [
        {"label": "ABUSE", "confidence": 0.99},
        {
            "label": "ABUSE",
            "confidence": 0.99,
            "has_substance": True,
            "violations": [{"rule_id": "ABUSE", "evidence": "text"}],
        },
    ],
)
def test_drop_requires_evidence_and_no_substance_for_pure_abuse(payload):
    result = validate_output(json.dumps(payload), GuardSettings(), original="text")
    assert result.action == "REVIEW"
    assert result.reason == "missing_evidence"


def test_fabricated_evidence_is_invalid():
    from app.services.ai_policy import AIProcessingError

    with pytest.raises(AIProcessingError):
        validate_output(
            json.dumps(
                {
                    "label": "SPAM",
                    "confidence": 0.99,
                    "violations": [{"rule_id": "SPAM", "evidence": "not present"}],
                }
            ),
            GuardSettings(),
            original="actual text",
        )


def test_grounded_pure_abuse_evidence_is_accepted():
    result = validate_output(
        json.dumps(
            {
                "label": "ABUSE",
                "confidence": 0.99,
                "has_substance": False,
                "violations": [{"rule_id": "ABUSE", "evidence": "کسکش"}],
            }
        ),
        GuardSettings(),
        original="خیلی کسکشی",
    )
    assert result.action == "DROP"
    assert result.violations == (("ABUSE", "کسکش"),)


@pytest.mark.asyncio
async def test_policy_snapshot_is_unchanged_between_stages(model, monkeypatch):
    initial = ai_service.compact_prompt()

    async def analyze(*args, **kwargs):
        monkeypatch.setattr(
            ai_service, "settings", replace(ai_service.settings, ai_guardrails="new policy")
        )
        return decision(Label.OK)

    model[0].side_effect = analyze
    await moderation_service.moderate(1, 1, "unknown message")
    assert model[1].call_args.kwargs["policy"] == initial


@pytest.mark.asyncio
async def test_cancellation_does_not_become_publish_or_leave_budget(model):
    model[0].side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await moderation_service.moderate(1, 1, "unknown message")
    assert active_budget.get() is None
