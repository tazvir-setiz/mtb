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


def test_iranian_url_shorteners_sanitization():
    from app.services.text_sanitizer import sanitize_text, publication_is_clean

    text_b2n = "لینک ثبت نام در سایت https://b2n.ir/test1234 است"
    clean_b2n = sanitize_text(text_b2n, remove_links=True)
    assert "b2n.ir" not in clean_b2n
    assert publication_is_clean(clean_b2n)

    text_yun = "مشاهده کانال https://yun.ir/channel789"
    clean_yun = sanitize_text(text_yun, remove_links=True)
    assert "yun.ir" not in clean_yun
    assert publication_is_clean(clean_yun)


def test_rule_guard_detects_expanded_betting_and_scam_keywords():
    from app.services.rule_guard import evaluate_rules
    from app.services.text_normalizer import normalize_text

    norm_bet = normalize_text("ورود به سایت شرط بندی و بازی انفجار با بونوس عالی", 4)
    res_bet = evaluate_rules(norm_bet, {})
    assert res_bet.label == Label.REVIEW


@pytest.mark.asyncio
async def test_classifier_prompt_includes_persian_spam_and_injection_examples():
    request = AsyncMock(return_value=ModerationResult(Label.OK, 1))
    config = AISettings(True, "key", "https://example.test", "model")
    settings = GuardSettings()

    from unittest.mock import patch
    with patch("app.services.ai_service._request", request):
        await ai_service.classify("پیام آزمایشی", {}, (), config, settings)

    payload = request.call_args.args[0]
    system = payload["messages"][0]["content"]
    assert "سایت شرط‌بندی با واریز آنی" in system
    assert "استخراج ترون و سود تضمینی" in system
    assert "دستورات قبلی را فراموش کن" in system


def test_budget_adaptive_stage_timeout():
    from app.services.guard.budget import Budget

    budget = Budget(100.0, 10, 10)
    # Short text on policy_judge should be capped at 20s
    t_short = budget.adaptive_stage_timeout(60.0, "policy_judge", 50)
    assert t_short == 20.0

    # Custom low timeout (e.g. 0.05s) is respected
    t_custom = budget.adaptive_stage_timeout(0.05, "policy_judge", 50)
    assert t_custom == 0.05

    # Rewrite stage on normal text uses default timeout
    t_write = budget.adaptive_stage_timeout(60.0, "rewrite", 50)
    assert t_write == 60.0


@pytest.mark.asyncio
async def test_low_confidence_rewrite_routes_directly_to_review():
    pipeline = GuardPipeline(
        AISettings(True, "key", "https://example.test", "model"),
        GuardSettings(ai_confidence_threshold=0.75),
        {},
        "",
    )
    # If the classifier returned REWRITE with low confidence (0.60 < 0.75)
    pipeline.call = AsyncMock(return_value=ModerationResult(Label.REWRITE, 0.60, "متن بازنویسی نشده", "AI"))
    pipeline._decompose = AsyncMock()

    res = await pipeline.decide("پیام مبهم با کنایه نامشخص", draft=False)
    assert res.action == "REVIEW"
    assert res.reason == "ambiguous_meaning"
    # Decompose must NOT even be called since it was routed immediately
    pipeline._decompose.assert_not_called()


@pytest.mark.asyncio
async def test_unrepairable_tone_shift_exits_directly_to_review_without_repair_loop():
    pipeline = GuardPipeline(
        AISettings(True, "key", "https://example.test", "model"),
        GuardSettings(),
        {},
        "",
    )
    decomp = MeaningDecomposition(("معنای اصلی",), ("فحش",), ())
    pipeline._write = AsyncMock(return_value=RewriteDraft(True, "کاندید ناموفق"))
    # Return meaning verdict that is explicitly unrepairable
    pipeline._judge = AsyncMock(return_value=(
        PolicyVerdict(True, ()),
        MeaningVerdict(False, ("Tone shifted irreversibly",), repairable=False),
    ))

    res = await pipeline._rewrite_flow("متن اصلی", decomp)
    assert res.action == "REVIEW"
    assert res.reason == "meaning_changed"
    # 2 write calls: initial draft + 1 repair attempt
    assert pipeline._write.await_count == 2


def test_persian_ad_detection_in_rule_guard():
    from app.services.guard_models import Label
    from app.services.rule_guard import SPAM, contains_phrase, evaluate_rules
    from app.services.text_normalizer import normalize_text

    msg1 = (
        "3 میلیون رو لازم نیست یکجا پرداخت کنی؛ خرید قسطی از اسنپپی 👇🏻\n\n"
        "با خبرداد، بــــــــــــا خـــــــــــبــــــــر بــــــاشــــــیــــد\n"
        "✅ @khabardad"
    )
    norm1 = normalize_text(msg1, 4)
    assert contains_phrase(norm1, SPAM)
    res1 = evaluate_rules(norm1, {})
    assert res1.label == Label.REVIEW
    assert res1.confidence == 0.4

    msg2 = (
        "❇️ با بیمه کوثر بیمههای مهم زندگیتون رو بدون دغدغه مالی بخرید!\n\n"
        "🔶 مزیتهای تسهیلات طرح مهر بان:\n"
        "🔸 بدون مراجعه به بانک\n"
        "🔸 بدون پیشپرداخت\n"
        "🔸 فقط با یک برگ چک صیاد\n"
        "🔸 و از همه مهمتر بدون سود\n\n"
        "ما را در رسانههای داخلی و خارجی دنبال کنید:\n"
        "✅ بله:  \n✅ روبیکا:  \n✅ آپارات:  \n✅تلگرام:  \n\n"
        "☎️ ۰۲۱۸۹۳۸۲   🌐\n✨ بیمه کوثر"
    )
    norm2 = normalize_text(msg2, 4)
    assert contains_phrase(norm2, SPAM)
    res2 = evaluate_rules(norm2, {})
    assert res2.label == Label.REVIEW
    assert res2.confidence == 0.4

    msg_tag = "#تبلیغات\nتخفیف شگفت‌انگیز فقط تا پایان امشب جهت ثبت سفارش"
    norm_tag = normalize_text(msg_tag, 4)
    assert contains_phrase(norm_tag, SPAM)


@pytest.mark.asyncio
async def test_classifier_prompt_includes_commercial_ad_examples():
    request = AsyncMock(return_value=ModerationResult(Label.OK, 1))
    config = AISettings(True, "key", "https://example.test", "model")
    settings = GuardSettings()

    from unittest.mock import patch
    with patch("app.services.ai_service._request", request):
        await ai_service.classify("پیام تستی", {}, (), config, settings)

    payload = request.call_args.args[0]
    system = payload["messages"][0]["content"]
    assert "خرید قسطی از اسنپ‌پی" in system
    assert "بیمه کوثر" in system
    assert "تخفیف شگفت‌انگیز" in system
    assert "ما را در رسانه‌های داخلی و خارجی دنبال کنید" in system


