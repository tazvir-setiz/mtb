from unittest.mock import AsyncMock

import pytest

from app.services import ai_service
from app.services.guard.contracts import RewriteDraft, Verification, validate_rewrite_draft
from app.services.guard_models import Label, ModerationResult
from app.services.guard.pipeline import GuardPipeline
from app.services.output_validator import validate_output
from app.services.text_normalizer import normalize_text
from app.services.rule_guard import evaluate_rules
from app.guard_config import GuardSettings


def test_classifier_rewrite_has_no_text():
    result = validate_output(
        '{"label":"REWRITE","confidence":0.97,"text":null,"has_substance":true}',
        GuardSettings(),
        original="متن",
    )
    assert result.label == Label.REWRITE
    assert result.text is None


def test_classifier_cannot_smuggle_rewrite_text():
    from app.services.ai_policy import AIProcessingError
    with pytest.raises(AIProcessingError):
        validate_output(
            '{"label":"REWRITE","confidence":0.97,"text":"متن جدید"}',
            GuardSettings(),
            original="متن",
        )


def test_writer_contract_has_no_moderation_label():
    draft = validate_rewrite_draft(
        '{"success":true,"text":"قیافه‌ات خیلی بد و زننده است.",'
        '"preserved_meaning":"قضاوت منفی درباره ظاهر","reason":null}',
        4000,
    )
    assert draft.success
    assert draft.text == "قیافه‌ات خیلی بد و زننده است."


@pytest.mark.parametrize(
    "text",
    [
        "خیلی قیافه ات کیریه",
        "کیا کیر منو میخوان بخورن تا من بهشون پول بدم",
        "کیا یه غذای کیری میخوان",
    ],
)
def test_meaningful_vulgar_sentences_are_not_locally_dropped(text):
    assert evaluate_rules(normalize_text(text), {}).action != "DROP"


@pytest.mark.asyncio
async def test_pipeline_uses_writer_after_classifier_requests_rewrite(monkeypatch):
    from app.services.ai_settings import AISettings

    classify = AsyncMock(
        return_value=ModerationResult(Label.REWRITE, 0.98, source="AI", has_substance=True)
    )
    writer = AsyncMock(
        return_value=RewriteDraft(
            True,
            "قیافه‌ات خیلی بد و زننده است.",
            "قضاوت منفی درباره ظاهر",
            None,
        )
    )
    verify = AsyncMock(return_value=Verification(True, True))

    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "generate_rewrite", writer)
    monkeypatch.setattr(ai_service, "verify", verify)

    pipeline = GuardPipeline(
        AISettings(True, "test", "https://example.test", "model"),
        GuardSettings(),
        {},
        "test policy",
    )
    result = await pipeline.run("خیلی قیافه ات کیریه")
    assert result.action == "PUBLISH"
    assert result.text == "قیافه‌ات خیلی بد و زننده است."
    writer.assert_awaited_once()
    verify.assert_awaited_once()


@pytest.mark.asyncio
async def test_writer_cannot_authorize_drop(monkeypatch):
    from app.services.ai_settings import AISettings

    classify = AsyncMock(
        side_effect=[
            ModerationResult(Label.ABUSE, 0.99, source="AI"),
            ModerationResult(Label.ABUSE, 0.99, source="AI"),
        ]
    )
    writer = AsyncMock(
        return_value=RewriteDraft(False, None, None, "no faithful rewrite")
    )

    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "generate_rewrite", writer)

    pipeline = GuardPipeline(
        AISettings(True, "test", "https://example.test", "model"),
        GuardSettings(),
        {},
        "test policy",
    )
    result = await pipeline.run("ناسزای صرف")
    # DROP comes from analyze + independent drop audit, not the writer.
    assert result.action == "DROP"
    assert classify.await_count == 2
    writer.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_verification_uses_writer_repair(monkeypatch):
    from app.services.ai_settings import AISettings

    classify = AsyncMock(
        return_value=ModerationResult(Label.REWRITE, 0.98, source="AI")
    )
    writer = AsyncMock(
        side_effect=[
            RewriteDraft(
                True,
                "کیا منو میخوان بخورن تا من بهشون پول بدم",
                "پرسش درباره رابطه",
                None,
            ),
            RewriteDraft(
                True,
                "چه کسانی انتظار دارند برای انجام چنین کار تحقیرآمیزی به آن‌ها پول بدهم؟",
                "پرسش درباره انتظار دریافت پول در برابر کاری تحقیرآمیز",
                None,
            ),
        ]
    )
    verify = AsyncMock(
        side_effect=[
            Verification(
                True,
                False,
                ("semantic relation changed by deleting the vulgar object",),
                True,
            ),
            Verification(True, True),
        ]
    )

    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "generate_rewrite", writer)
    monkeypatch.setattr(ai_service, "verify", verify)

    pipeline = GuardPipeline(
        AISettings(True, "test", "https://example.test", "model"),
        GuardSettings(),
        {},
        "test policy",
    )
    result = await pipeline.run("کیا کیر منو میخوان بخورن تا من بهشون پول بدم")
    assert result.action == "PUBLISH"
    assert "تحقیرآمیزی" in result.text
    assert writer.await_count == 2
    assert verify.await_count == 2
