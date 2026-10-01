import pytest
from guard_mocks import mock_guard

from app.services.ai_policy import AIReviewRequired
from app.services.ai_settings import save_ai_value
from app.services.guard.contracts import PolicyVerdict, RewriteDraft
from app.services.guard_models import Label, ModerationResult
from app.services.review_rewriter import rewrite_draft


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-key")
    return mock_guard(monkeypatch)


@pytest.mark.asyncio
async def test_requests_rewrite_even_for_locally_publishable_message(model):
    model.side_effect = [
        ModerationResult(Label.REWRITE, 0.99, "درود دوستان", "AI"),
        ModerationResult(Label.OK, 0.99, source="AI"),
    ]
    model.writer.return_value = RewriteDraft(True, "درود دوستان")
    assert await rewrite_draft("سلام دوستان") == "درود دوستان"
    model.assert_not_awaited()
    assert model.writer.call_args.args[0] == "سلام دوستان"
    assert model.policy.call_args.args[1] == "درود دوستان"
    assert model.semantic.call_args.args[1] == "درود دوستان"


@pytest.mark.asyncio
async def test_classification_without_rewrite_is_not_presented_as_new_draft(model):
    model.writer.return_value = RewriteDraft(False, reason="no faithful rewrite")
    with pytest.raises(AIReviewRequired, match="rewrite_failed"):
        await rewrite_draft("سلام دوستان")


@pytest.mark.asyncio
async def test_noncompliant_draft_is_not_returned(model):
    model.policy.return_value = PolicyVerdict(False, ("political advocacy",), False)
    model.side_effect = [
        ModerationResult(Label.REWRITE, 0.99, "پیش‌نویس نامناسب", "AI"),
        ModerationResult(Label.POLITICAL, 0.99, source="AI"),
    ]
    with pytest.raises(AIReviewRequired, match="rewrite_failed"):
        await rewrite_draft("متن اصلی")


@pytest.mark.asyncio
async def test_pure_abuse_recommends_drop_without_inventing_content(model):
    assert await rewrite_draft("خیلی کسکشی") == "__DROP__"
    model.assert_not_awaited()


@pytest.mark.asyncio
async def test_rewrite_outage_propagates_without_substituting_original(model):
    from app.services.ai_transport import AIRequestError

    model.writer.side_effect = AIRequestError("timeout")
    with pytest.raises(AIRequestError):
        await rewrite_draft("متن اصلی")
