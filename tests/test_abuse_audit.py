import pytest
from guard_mocks import mock_guard

from app.services import moderation_service
from app.services.ai_policy import AIProcessingError
from app.services.ai_settings import save_ai_value
from app.services.guard.contracts import PolicyVerdict, RewriteDraft
from app.services.guard_models import Label, ModerationResult
from app.services.guard_runtime import runtime
from app.services.review_rewriter import rewrite_draft

TEXT = "اینکه سطلی ها تمام سعیشون میکنن خودشون بچسبونن به صهیونیست خیلی خوبه، چون جفتشونم به رسمیت شناخته نمیشن و جز وحوش سطح یک دنیا هستن"


def result(label, text=None):
    return ModerationResult(label, 0.95, text, "AI")


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-key")
    return mock_guard(monkeypatch)


@pytest.mark.asyncio
async def test_false_abuse_can_be_rewritten_and_verified(model):
    model.side_effect = [
        result(Label.ABUSE),
        result(Label.REWRITE, "نظر بازنویسی‌شده"),
        result(Label.OK),
    ]
    model.writer.return_value = RewriteDraft(True, "نظر بازنویسی‌شده")
    decision = await moderation_service.moderate(1, 145, TEXT)
    assert decision.action == "PUBLISH"
    assert decision.text == "نظر بازنویسی‌شده"
    assert model.call_args_list[1].kwargs["audit_drop"] is True
    assert model.policy.call_args.args[1] == decision.text
    assert model.semantic.call_args.args[1] == decision.text
    assert runtime.metrics["stage_drop_audit"] == 1


@pytest.mark.asyncio
async def test_audit_can_release_compliant_original(model):
    model.side_effect = [result(Label.ABUSE), result(Label.OK)]
    decision = await moderation_service.moderate(1, 1, TEXT)
    assert decision.text == TEXT
    assert decision.action == "PUBLISH"


@pytest.mark.asyncio
async def test_confirmed_ai_abuse_is_not_cached(model):
    model.return_value = result(Label.ABUSE)
    for message_id in (1, 2):
        assert (await moderation_service.moderate(1, message_id, TEXT)).action == "DROP"
    assert model.await_count == 4
    model.writer.assert_not_awaited()
    assert not runtime.cache


@pytest.mark.asyncio
async def test_failed_audit_does_not_silently_drop_or_publish(model):
    model.side_effect = [result(Label.ABUSE), AIProcessingError("offline")]
    decision = await moderation_service.moderate(1, 1, TEXT)
    assert decision.action == "REVIEW"
    assert decision.source == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_abuse_from_reassessment_also_needs_audit(model):
    model.side_effect = [result(Label.REVIEW), result(Label.ABUSE), result(Label.OK)]
    assert (await moderation_service.moderate(1, 1, TEXT)).action == "PUBLISH"
    assert model.call_args_list[2].kwargs["audit_drop"] is True


@pytest.mark.asyncio
async def test_manual_rewrite_also_reconsiders_false_abuse(model):
    model.side_effect = [result(Label.ABUSE), result(Label.REWRITE, "پیش‌نویس"), result(Label.OK)]
    assert await rewrite_draft(TEXT) == "پیش‌نویس"
    model.assert_not_awaited()  # Explicit rewrite goes directly to decomposition and drafting.
    model.meaning.assert_awaited_once()
    model.policy.assert_awaited_once()
    model.semantic.assert_awaited_once()


@pytest.mark.asyncio
async def test_audited_rewrite_must_still_pass_final_check(model):
    model.policy.return_value = PolicyVerdict(False, ("political advocacy",), False)
    model.side_effect = [
        result(Label.ABUSE),
        result(Label.REWRITE, "نامناسب"),
        result(Label.POLITICAL),
    ]
    decision = await moderation_service.moderate(1, 1, TEXT)
    assert decision.action == "REVIEW"
    assert decision.reason == "rewrite_failed"
