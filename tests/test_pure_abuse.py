from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from guard_mocks import mock_guard

from app.guard_config import GuardSettings
from app.services import moderation_service, review_store
from app.services.ai_settings import save_ai_value
from app.services.context_manager import update_context
from app.services.guard.contracts import (
    RewriteDraft,
)
from app.services.guard_models import Label, ModerationResult
from app.services.output_validator import validate_output
from app.services.rule_guard import evaluate_rules
from app.services.text_normalizer import normalize_text
from app.telegram import message_sender


@pytest.fixture
def ai(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-key")
    return mock_guard(monkeypatch)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "خیلی کسکشی",
        "تو خیلی کسکش هستی!",
        "كِس‌كش",
        "<b>خیلی کسکشی</b>",
        "کسکش",
        "fuck you!",
    ],
)
async def test_clear_pure_abuse_drops_without_ai_even_with_political_context(ai, text):
    update_context(1, {"political": True}, "دولت", GuardSettings())
    result = await moderation_service.moderate(1, 142, text)
    assert result.label == Label.ABUSE
    assert result.action == "DROP"
    ai.assert_not_awaited()


@pytest.mark.parametrize(
    "text",
    [
        "خیلی دوستت دارم مثل کیر",
        "او گفت «خیلی کسکشی»",
        "«خیلی کسکشی»",
        "<blockquote>خیلی کسکشی</blockquote>",
        "<code>کسکش</code>",
        "کسکش نیستی",
        "نگو کسکش",
        "واژه کسکش توهین‌آمیز است",
        "کسکشی نکن",
        "کسکش! جلسه فردا ساعت ده است",
        "کیرکگور فیلسوف بود",
        "کسکش؟ نه",
    ],
)
def test_meaningful_quoted_negated_or_substring_matches_are_not_locally_dropped(text):
    assert evaluate_rules(normalize_text(text), {}).action != "DROP"


@pytest.mark.asyncio
async def test_pure_abuse_is_not_sent_or_added_to_admin_queue(ai):
    original = SimpleNamespace(id=142, message="خیلی کسکشی", entities=[], media=None, poll=None)
    client = SimpleNamespace(send_message=AsyncMock())
    assert await message_sender.send_message(client, original, 1, 2, None) is None
    client.send_message.assert_not_awaited()
    ai.assert_not_awaited()
    assert review_store.pending() == []


@pytest.mark.asyncio
async def test_model_can_drop_other_pure_insults_without_review(ai):
    ai.return_value = validate_output('{"label":"ABUSE","confidence":0.99}', GuardSettings())
    result = await moderation_service.moderate(1, 1, "ناسزای خارج از قواعد محلی")
    assert result.action == "DROP"
    assert ai.await_count == 2
    assert ai.call_args.kwargs["audit_drop"] is True
    ai.writer.assert_not_awaited()


def test_uncertain_ai_abuse_does_not_automatically_drop():
    result = validate_output('{"label":"ABUSE","confidence":0.7}', GuardSettings())
    assert result.action == "REVIEW"


@pytest.mark.asyncio
async def test_substantive_abusive_message_still_gets_verified_rewrite(ai):
    ai.side_effect = [
        ModerationResult(Label.REWRITE, 0.99, "خیلی دوستت دارم.", "AI"),
        ModerationResult(Label.OK, 0.99, source="AI"),
    ]
    ai.writer.return_value = RewriteDraft(True, "خیلی دوستت دارم.")
    result = await moderation_service.moderate(1, 1, "خیلی دوستت دارم مثل کیر")
    assert result.action == "PUBLISH"
    assert result.text == "خیلی دوستت دارم."
    assert ai.await_count == 1
    ai.policy.assert_awaited_once()
    ai.semantic.assert_awaited_once()
