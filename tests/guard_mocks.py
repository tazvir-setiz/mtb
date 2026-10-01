"""Provider mocks for the split Guard v4 stages (the pipeline itself stays real)."""

from unittest.mock import AsyncMock

from app.services import ai_service
from app.services.guard.contracts import (
    MeaningDecomposition,
    MeaningVerdict,
    PolicyVerdict,
    RewriteDraft,
)
from app.services.guard_models import Label, ModerationResult


def mock_guard(monkeypatch):
    classifier = AsyncMock(return_value=ModerationResult(Label.REVIEW, 0.9, source="AI"))
    classifier.meaning = AsyncMock(return_value=MeaningDecomposition(("protected claim",), (), ()))
    classifier.writer = AsyncMock(return_value=RewriteDraft(True, "پیش‌نویس"))
    classifier.policy = AsyncMock(return_value=PolicyVerdict(True))
    classifier.semantic = AsyncMock(return_value=MeaningVerdict(True))
    for name, mock in (
        ("classify", classifier),
        ("decompose_meaning", classifier.meaning),
        ("generate_rewrite", classifier.writer),
        ("judge_policy", classifier.policy),
        ("judge_meaning", classifier.semantic),
    ):
        monkeypatch.setattr(ai_service, name, mock)
    monkeypatch.setattr(
        "app.services.guard.pipeline.search_latest_news", AsyncMock(return_value=[])
    )
    return classifier
