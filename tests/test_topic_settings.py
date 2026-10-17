from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.handlers import topic_settings
from app.handlers.router import on_text
from app.handlers.states import State, get_state, set_state
from app.services.ai_policy import AI_DROP_RESULT, AIReviewRequired
from app.services.ai_service import apply_ai_guardrails
from app.services.ai_settings import format_topic_policy, load_ai_settings, save_ai_value
from app.services.guard_models import Label, ModerationResult
from app.services.output_validator import validate_output
from app.guard_config import guard_settings


def make_update(text="", user_id=None, chat_type="private"):
    admin_id = settings.admin_ids[0] if settings.admin_ids else 111
    uid = user_id if user_id is not None else admin_id
    message = SimpleNamespace(text=text, reply_text=AsyncMock(), delete=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=uid),
        effective_chat=SimpleNamespace(type=chat_type),
        effective_message=message,
        message=message,
        callback_query=None,
    )


def test_format_topic_policy():
    policy_drop = format_topic_policy(("هوش مصنوعی", "تکنولوژی"), "DROP")
    assert "SPAM" in policy_drop
    assert "هوش مصنوعی" in policy_drop
    assert "off_topic" in policy_drop

    policy_review = format_topic_policy(("بازار مالی",), "REVIEW")
    assert "REVIEW" in policy_review
    assert "بازار مالی" in policy_review

    assert format_topic_policy(()) == ""


def test_output_validator_off_topic_support():
    # DROP action with off_topic rule
    raw_drop = (
        '{"label":"SPAM","confidence":0.95,"text":null,"has_substance":true,'
        '"violations":[{"rule_id":"off_topic","evidence":"off_topic"}],'
        '"ambiguities":["off_topic"]}'
    )
    result_drop = validate_output(raw_drop, guard_settings, original="متن پیام نامرتبط")
    assert result_drop.label == Label.SPAM
    assert result_drop.action == "DROP"
    assert result_drop.reason == "off_topic"

    # REVIEW action with off_topic ambiguities
    raw_review = (
        '{"label":"REVIEW","confidence":0.95,"text":null,"has_substance":true,'
        '"violations":[],"ambiguities":["off_topic"]}'
    )
    result_review = validate_output(raw_review, guard_settings, original="متن نامشخص")
    assert result_review.label == Label.REVIEW
    assert result_review.action == "REVIEW"
    assert result_review.reason == "off_topic"


@pytest.mark.asyncio
async def test_topic_settings_handlers_flow():
    context = SimpleNamespace(user_data={})

    # Show menu
    update = make_update()
    await topic_settings.show(update, context)
    assert update.effective_message.reply_text.called
    text = update.effective_message.reply_text.call_args[0][0]
    assert "فیلترینگ موضوعی" in text

    # Toggle enabled
    current = load_ai_settings().topic_filter_enabled
    await topic_settings.toggle(update, context)
    assert load_ai_settings().topic_filter_enabled is not current

    # Toggle action
    save_ai_value("off_topic_action", "DROP")
    await topic_settings.toggle_action(update, context)
    assert load_ai_settings().off_topic_action == "REVIEW"
    await topic_settings.toggle_action(update, context)
    assert load_ai_settings().off_topic_action == "DROP"

    # Ask for topics input
    await topic_settings.ask(update, context)
    assert get_state(context.user_data) == State.TOPIC_INPUT

    # Save topics with Persian comma via router
    update_input = make_update("تکنولوژی، هوش مصنوعی، ارز دیجیتال")
    await on_text(update_input, context)
    assert get_state(context.user_data) == State.MAIN_MENU
    saved = load_ai_settings()
    assert saved.target_topics == ("تکنولوژی", "هوش مصنوعی", "ارز دیجیتال")

    # Clear topics
    await topic_settings.clear(update, context)
    assert load_ai_settings().target_topics == ()


@pytest.mark.asyncio
async def test_apply_ai_guardrails_off_topic_drop_and_review(monkeypatch):
    # When off_topic and DROP -> returns AI_DROP_RESULT
    async def mock_moderate_drop(*args, **kwargs):
        return ModerationResult(label=Label.SPAM, confidence=0.98, reason="off_topic")

    monkeypatch.setattr("app.services.moderation_service.moderate", mock_moderate_drop)
    res = await apply_ai_guardrails("پیام غیرمرتبط")
    assert res == AI_DROP_RESULT

    # When off_topic and REVIEW -> raises AIReviewRequired("off_topic")
    async def mock_moderate_review(*args, **kwargs):
        return ModerationResult(label=Label.REVIEW, confidence=0.98, reason="off_topic")

    monkeypatch.setattr("app.services.moderation_service.moderate", mock_moderate_review)
    with pytest.raises(AIReviewRequired) as exc_info:
        await apply_ai_guardrails("پیام غیرمرتبط")
    assert "off_topic" in str(exc_info.value)
