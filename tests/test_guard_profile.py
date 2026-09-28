import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers import guard_settings as handlers
from app.handlers.states import State, reset
from app.services import ai_service, moderation_service
from app.services.ai_settings import save_ai_value
from app.services.guard.contracts import Verification
from app.services.guard_models import Label, ModerationResult
from app.services.guard_profile import (
    BOUNDS,
    MAX_FILE_BYTES,
    decode_profile,
    default_profile,
    encode_profile,
    load_profile,
    revision,
    save_profile,
    validate_profile,
)
from app.services.guard_runtime import runtime


def persist(profile):
    save_profile(profile, revision(load_profile()))


def update_for(profile=None, user=111, chat="private"):
    raw = encode_profile(profile or default_profile())
    file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(raw)))
    doc = SimpleNamespace(
        file_name="settings.json", file_size=len(raw), get_file=AsyncMock(return_value=file)
    )
    msg = SimpleNamespace(document=doc, reply_text=AsyncMock(), reply_document=AsyncMock())
    update = SimpleNamespace(
        message=msg,
        effective_message=msg,
        effective_user=SimpleNamespace(id=user),
        effective_chat=SimpleNamespace(type=chat),
        callback_query=None,
    )
    return update, SimpleNamespace(user_data={"state": State.GUARD_IMPORT})


def test_roundtrip_persistence_and_no_credentials():
    profile = default_profile()
    profile["instructions"] = "انتساب خبر به گوینده حفظ شود."
    profile["sensitivity"]["political"] = "off"
    profile["limits"]["timeout_seconds"] = 80
    persist(profile)
    assert load_profile() == profile
    raw = encode_profile(load_profile())
    assert decode_profile(raw) == profile
    assert b"api_key" not in raw and b"BOT_TOKEN" not in raw


@pytest.mark.parametrize("name", list(BOUNDS))
def test_all_limits_reject_bad_types_and_values(name):
    for value in (True, "5", -1, float("nan"), float("inf"), BOUNDS[name][1] + 1):
        profile = default_profile()
        profile["limits"][name] = value
        with pytest.raises(ValueError):
            validate_profile(profile)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":1,"version":1}',
        b"[]",
        b"null",
        b"\xff",
        b"{" * 2000,
        b" " * (MAX_FILE_BYTES + 1),
    ],
    ids=["duplicate", "array", "null", "encoding", "nesting", "oversized"],
)
def test_invalid_files_rejected(raw):
    with pytest.raises(ValueError):
        decode_profile(raw)


def test_unknown_fields_missing_fields_and_budget_relationships():
    original = default_profile()
    variants = []
    for section in (None, "limits", "sensitivity"):
        profile = copy.deepcopy(original)
        (profile if section is None else profile[section])["unknown"] = 1
        variants.append(profile)
    profile = copy.deepcopy(original)
    del profile["limits"]["cache_size"]
    variants.append(profile)
    profile = copy.deepcopy(original)
    profile["limits"]["total_timeout_seconds"] = 1
    variants.append(profile)
    profile = copy.deepcopy(original)
    profile["limits"]["max_requests"] = 1
    variants.append(profile)
    for profile in variants:
        with pytest.raises(ValueError):
            persist(profile)
        assert load_profile() == original


def test_stale_revision_rejected_and_cache_cleared():
    original = load_profile()
    changed = copy.deepcopy(original)
    changed["sensitivity"]["abuse"] = "off"
    runtime.cache["old"] = (1, None)
    persist(changed)
    assert not runtime.cache
    with pytest.raises(ValueError):
        save_profile(original, revision(original))
    assert load_profile() == changed


@pytest.mark.asyncio
async def test_import_requires_confirmation_and_old_button_cannot_reapply():
    profile = default_profile()
    profile["instructions"] = "خبر را کوتاه و با حفظ معنا منتشر کن."
    update, context = update_for(profile)
    await handlers.receive(update, context)
    assert load_profile() != profile
    token = context.user_data["guard_pending"][0]
    update.callback_query = SimpleNamespace(
        data=f"guard:apply:{token}", edit_message_text=AsyncMock()
    )
    await handlers.apply(update, context)
    assert load_profile() == profile
    assert "guard_pending" not in context.user_data
    await handlers.apply(update, context)
    assert "منقضی" in update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("user,chat", [(999, "private"), (111, "group")])
async def test_only_private_admin_can_download_or_upload(user, chat):
    update, context = update_for(user=user, chat=chat)
    await handlers.receive(update, context)
    await handlers.export(update, context)
    update.message.document.get_file.assert_not_awaited()
    update.message.reply_document.assert_not_awaited()
    assert "guard_pending" not in context.user_data


@pytest.mark.asyncio
async def test_oversized_document_not_downloaded():
    update, context = update_for()
    update.message.document.file_size = MAX_FILE_BYTES + 1
    await handlers.receive(update, context)
    update.message.document.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_discards_pending_profile():
    profile = default_profile()
    profile["sensitivity"]["spam"] = "strict"
    update, context = update_for(profile)
    await handlers.receive(update, context)
    reset(context.user_data)
    assert "guard_pending" not in context.user_data
    assert load_profile() != profile


@pytest.fixture
def model(monkeypatch):
    save_ai_value("enabled", "true")
    save_ai_value("api_key", "test")
    classify = AsyncMock(return_value=ModerationResult(Label.OK, 0.99, source="AI"))
    verify = AsyncMock(return_value=Verification(True, True))
    monkeypatch.setattr(ai_service, "classify", classify)
    monkeypatch.setattr(ai_service, "verify", verify)
    return classify, verify


@pytest.mark.asyncio
async def test_abuse_off_bypasses_local_drop_and_uses_same_policy_for_verification(model):
    profile = load_profile()
    profile["sensitivity"]["abuse"] = "off"
    profile["limits"]["max_output_tokens"] = 2048
    persist(profile)
    result = await moderation_service.moderate(1, 1, "خیلی کسکشی")
    assert result.action == "PUBLISH"
    call = model[0].call_args
    assert '"abuse": "off"' in call.kwargs["policy"]
    assert call.args[4].max_output_tokens == 2048
    assert model[1].call_args.kwargs["policy"] == call.kwargs["policy"]


@pytest.mark.asyncio
async def test_model_cannot_drop_using_disabled_category(model):
    profile = load_profile()
    profile["sensitivity"]["abuse"] = "off"
    persist(profile)
    model[0].return_value = ModerationResult(Label.ABUSE, 0.99, source="AI")
    result = await moderation_service.moderate(1, 1, "خیلی کسکشی")
    assert result.action == "REVIEW"
    assert result.reason == "policy_mismatch"


@pytest.mark.asyncio
async def test_custom_rules_apply_to_local_greetings_and_drafts(model):
    profile = load_profile()
    profile["instructions"] = "Avoid greetings."
    persist(profile)
    await moderation_service.moderate(1, 1, "سلام")
    assert "Avoid greetings." in model[0].call_args.kwargs["policy"]
    model[0].return_value = ModerationResult(Label.REWRITE, 0.99, "سلام دوستان", "AI")
    await moderation_service.moderate(1, 2, "سلام", draft=True)
    assert model[0].call_args.kwargs["rewrite"]
    assert "Avoid greetings." in model[1].call_args.kwargs["policy"]


@pytest.mark.asyncio
async def test_policy_change_during_request_keeps_snapshot(model):
    profile = load_profile()
    profile["instructions"] = "OLD POLICY"
    persist(profile)

    async def change_policy(*args, **kwargs):
        newer = load_profile()
        newer["instructions"] = "NEW POLICY"
        persist(newer)
        return ModerationResult(Label.OK, 0.99, source="AI")

    model[0].side_effect = change_policy
    await moderation_service.moderate(1, 1, "متن آزمایش")
    assert "OLD POLICY" in model[1].call_args.kwargs["policy"]
    assert "NEW POLICY" not in model[1].call_args.kwargs["policy"]
    await moderation_service.moderate(1, 2, "متن آزمایش")
    assert "NEW POLICY" in model[0].call_args.kwargs["policy"]


@pytest.mark.asyncio
async def test_stale_admin_confirmation_does_not_overwrite_newer_change():
    first = load_profile()
    first["sensitivity"]["spam"] = "strict"
    update, context = update_for(first)
    await handlers.receive(update, context)
    token = context.user_data["guard_pending"][0]
    newer = load_profile()
    newer["instructions"] = "New administrator policy"
    persist(newer)
    update.callback_query = SimpleNamespace(
        data=f"guard:apply:{token}", edit_message_text=AsyncMock()
    )
    await handlers.apply(update, context)
    assert load_profile() == newer
    assert "guard_pending" not in context.user_data


@pytest.mark.asyncio
async def test_downloaded_bytes_are_validated_even_if_metadata_is_wrong():
    update, context = update_for()
    file = update.message.document.get_file.return_value
    file.download_as_bytearray.return_value = b" " * (MAX_FILE_BYTES + 1)
    await handlers.receive(update, context)
    assert "guard_pending" not in context.user_data
    assert "۶۴" in update.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_new_upload_is_not_accepted_outside_import_state():
    update, context = update_for()
    reset(context.user_data)
    await handlers.receive(update, context)
    update.message.document.get_file.assert_not_awaited()


def test_saved_profile_replaces_environment_editorial_rules(monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(
        ai_service, "settings", replace(ai_service.settings, ai_guardrails="OLD ENV POLICY")
    )
    assert "OLD ENV POLICY" in ai_service.compact_prompt()
    profile = load_profile()
    profile["instructions"] = "NEW SAVED POLICY"
    persist(profile)
    prompt = ai_service.compact_prompt()
    assert "NEW SAVED POLICY" in prompt
    assert "OLD ENV POLICY" not in prompt


@pytest.mark.asyncio
async def test_changed_threshold_reaches_output_validator(model):
    from app.services.output_validator import validate_output

    profile = load_profile()
    profile["limits"]["ai_confidence_threshold"] = 0.95
    persist(profile)

    async def classify(text, context, candidates, config, limits, **kwargs):
        return validate_output('{"label":"OK","confidence":0.90}', limits, original=text)

    model[0].side_effect = classify
    result = await moderation_service.moderate(1, 1, "متن نیازمند تحلیل")
    assert result.action == "REVIEW"


def test_enormous_integer_is_validation_error():
    profile = default_profile()
    profile["limits"]["cache_size"] = 10**1000
    with pytest.raises(ValueError):
        decode_profile(encode_profile(profile))


def test_documented_example_matches_supported_schema():
    from dataclasses import asdict
    from pathlib import Path

    from app.guard_config import GuardSettings

    profile = decode_profile(
        (Path(__file__).resolve().parents[1] / "docs/guard-settings.example.json").read_bytes()
    )
    assert profile["limits"] == asdict(GuardSettings())
