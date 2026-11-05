import pytest
from guard_mocks import mock_guard

from app.guard_config import GuardSettings
from app.services import moderation_service
from app.services.ai_settings import format_topic_policy, save_ai_value
from app.services.guard.contracts import MeaningVerdict, PolicyVerdict, RewriteDraft
from app.services.guard_models import Label, ModerationResult
from app.services.output_validator import validate_output


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test-api-key")
    return mock_guard(monkeypatch)


def test_validate_output_persian_fuzzy_evidence():
    # Persian text with different unicode half-space / spelling variations
    original = "این پیام حاوی کلمات رکیک و بی‌ادبی است."
    # Evidence without ZWNJ or using Arabic Kaf/Yeh
    raw = (
        '{"label":"ABUSE","confidence":0.95,"has_substance":false,'
        '"violations":[{"rule_id":"abuse","evidence":"بی ادبی"}],'
        '"ambiguities":[]}'
    )
    result = validate_output(raw, GuardSettings(), original=original)
    assert result.label == Label.ABUSE
    assert result.action == "DROP"


def test_validate_output_single_pass_json_schema():
    raw = (
        '{"action":"REWRITE","label":"REWRITE","reason":"پالایش الفاظ و حفظ خبر",'
        '"topic":"اخبار داخلی","rewritten_text":"جلسه مجلس فردا صبح برگزار خواهد شد.",'
        '"confidence":0.95}'
    )
    result = validate_output(raw, GuardSettings(), original="جلسه مجلس فردا صبح برگزار خواهد شد احمق ها")
    assert result.action == "PUBLISH"
    assert result.label == Label.REWRITE
    assert result.text == "جلسه مجلس فردا صبح برگزار خواهد شد."
    assert result.reason == "پالایش الفاظ و حفظ خبر"


@pytest.mark.asyncio
async def test_pure_abuse_without_news_is_dropped(model):
    # Pure abuse with no substantive content -> DROP
    model.side_effect = [
        ModerationResult(Label.ABUSE, 0.98, source="AI", has_substance=False),
        ModerationResult(Label.ABUSE, 0.98, source="AI", has_substance=False),
    ]
    res = await moderation_service.moderate(1, 10, "احمق‌های بیشعور")
    assert res.action == "DROP"


@pytest.mark.asyncio
async def test_mixed_abuse_with_news_is_rewritten(model):
    # Message with insult + actual news -> REWRITE
    model.side_effect = [
        ModerationResult(
            Label.REWRITE, 0.96, text="ساعت شروع مسابقه ۱۸ اعلام شد.", source="AI"
        )
    ]
    model.writer.return_value = RewriteDraft(True, "ساعت شروع مسابقه ۱۸ اعلام شد.")
    res = await moderation_service.moderate(1, 11, "ساعت شروع مسابقه ۱۸ اعلام شد کثافت‌ها")
    assert res.action == "PUBLISH"
    assert res.label == Label.REWRITE
    assert res.text == "ساعت شروع مسابقه ۱۸ اعلام شد."


@pytest.mark.asyncio
async def test_topic_filter_drop_off_topic_immediately(model):
    save_ai_value("topic_filter_enabled", "true")
    save_ai_value("target_topics", "ورزش, فوتبال")
    save_ai_value("off_topic_action", "DROP")

    # Simulate off-topic detection
    model.side_effect = [
        ModerationResult(
            Label.SPAM,
            0.95,
            source="AI",
            reason="off_topic",
            violations=(("off_topic", "off_topic"),),
            ambiguities=("off_topic",),
        )
    ]
    res = await moderation_service.moderate(1, 12, "قیمت طلا و سکه امروز صعودی شد.")
    assert res.action == "DROP"
    assert res.reason == "off_topic"
    # Off-topic should return immediately without drop_audit
    assert model.call_count == 1

    # Cleanup
    save_ai_value("topic_filter_enabled", "false")
    save_ai_value("target_topics", "")
