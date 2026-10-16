from unittest.mock import AsyncMock
import pytest

from app.guard_config import GuardSettings
from app.services import ai_service
from app.services.ai_settings import AISettings
from app.services.guard.contracts import (
    MeaningDecomposition,
    MeaningVerdict,
    PolicyVerdict,
    RewriteDraft,
)
from app.services.guard.pipeline import GuardPipeline
from app.services.guard_models import Label, ModerationResult


@pytest.mark.asyncio
async def test_decompose_meaning_prompt_includes_persian_slang_and_humor():
    request = AsyncMock(return_value=MeaningDecomposition(("کنایه به ادعای جدید", "ایموجی 😂"), ("چسی",), ()))
    config = AISettings(True, "key", "https://example.test", "model")
    settings = GuardSettings()
    
    # We patch _request to capture the system prompt
    from unittest.mock import patch
    with patch("app.services.ai_service._request", request):
        await ai_service.decompose_meaning("چسی جدید کتاب های کمک درسی 😂", {}, (), config, settings)
    
    payload = request.call_args.args[0]
    system = payload["messages"][0]["content"]
    assert "SLANG, COLLOQUIAL IRONY, AND HUMOROUS TEASING" in system
    assert "چسی" in system
    assert "😂" in system


@pytest.mark.asyncio
async def test_rewrite_generator_prompt_protects_humor_and_bans_defamation():
    request = AsyncMock(return_value=RewriteDraft(True, "پز جدید کتاب های کمک درسی 😂 کتابهای ماجرای ۲۰"))
    config = AISettings(True, "key", "https://example.test", "model")
    settings = GuardSettings()
    
    decomp = MeaningDecomposition(("کنایه به ادعای جدید", "ایموجی 😂"), ("چسی",), ())
    from unittest.mock import patch
    with patch("app.services.ai_service._request", request):
        await ai_service.generate_rewrite("چسی جدید کتاب های کمک درسی 😂", decomp, {}, config, settings)
        
    payload = request.call_args.args[0]
    system = payload["messages"][0]["content"]
    assert "MINIMAL EDIT & TONE PRESERVATION FOR SLANG AND HUMOR" in system
    assert "خیلی بد هستند" in system
    assert "defamatory" in system


@pytest.mark.asyncio
async def test_judge_meaning_prompt_includes_tone_humor_defamation_check():
    request = AsyncMock(return_value=MeaningVerdict(True, ()))
    config = AISettings(True, "key", "https://example.test", "model")
    settings = GuardSettings()
    
    decomp = MeaningDecomposition(("کنایه به ادعای جدید", "ایموجی 😂"), ("چسی",), ())
    from unittest.mock import patch
    with patch("app.services.ai_service._request", request):
        await ai_service.judge_meaning(
            "چسی جدید کتاب های کمک درسی 😂",
            "پز جدید کتاب های کمک درسی 😂",
            decomp,
            {},
            config,
            settings,
        )
        
    payload = request.call_args.args[0]
    system = payload["messages"][0]["content"]
    assert "TONE, HUMOR & DEFAMATION CHECK" in system
    assert "defamation" in system


@pytest.mark.asyncio
async def test_slang_rewrite_failure_routes_to_review_not_defamatory_publish():
    # If the candidate rewrite inverts meaning and judge rejects it, pipeline must route to REVIEW
    original = "چسی جدید کتاب های کمک درسی 😂\nکتابهای ماجرای ۲۰"
    decomp = MeaningDecomposition(("کنایه به ادعای جدید", "ایموجی 😂"), ("چسی",), ())
    
    pipeline = GuardPipeline(
        AISettings(True, "key", "https://example.test", "model"),
        GuardSettings(),
        {},
        "",
    )
    
    # Mock decompose
    pipeline._decompose = AsyncMock(return_value=decomp)
    
    # Mock write returning a flawed defamatory candidate
    pipeline._write = AsyncMock(return_value=RewriteDraft(True, "کتابهای ماجرای ۲۰ خیلی بد هستند."))
    
    # Mock judge: policy passes (no curse words), but meaning judge FAILS because tone was inverted into defamation
    pipeline._judge = AsyncMock(return_value=(
        PolicyVerdict(True, ()),
        MeaningVerdict(False, ("Tone inverted from humor into defamation; emoji lost.",)),
    ))
    
    res = await pipeline._rewrite_flow(original, decomp)
    assert res.action == "REVIEW"
    assert res.reason == "meaning_changed"
