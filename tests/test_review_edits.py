from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai_policy import AI_DROP_RESULT
from app.handlers import review_edit, reviews
from app.handlers.states import State, reset
from app.services import review_drafts, review_service, review_store
from app.services.ai_settings import save_ai_value


def original(text="متن اولیه"):
    return SimpleNamespace(id=7, message=text, entities=[], media=None, poll=None)


def queued():
    return review_store.enqueue(original(), -100123, -100456, None, "review")


@pytest.mark.asyncio
async def test_edited_draft_requires_new_approval_and_sends_saved_text():
    row = queued()
    version = review_drafts.version(row)
    assert review_drafts.save(row.id, version, "متن ویرایش‌شده", "manual_draft")
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[original()]),
        send_message=AsyncMock(return_value=SimpleNamespace(id=90)),
    )
    await review_service.decide(row.id, version, "approve", 111, client)
    client.send_message.assert_not_awaited()
    fresh = review_store.get(row.id)
    await review_service.decide(row.id, review_drafts.version(fresh), "approve", 111, client)
    assert client.send_message.call_args.kwargs["message"] == "متن ویرایش‌شده"
    assert review_store.get(row.id).status == "sent"


def test_stale_editor_cannot_overwrite_another_admins_edit():
    row = queued()
    version = review_drafts.version(row)
    assert review_drafts.save(row.id, version, "first", "manual_draft")
    assert not review_drafts.save(row.id, version, "stale", "manual_draft")
    assert review_drafts.get(row.id).text == "first"


@pytest.mark.asyncio
async def test_source_change_discards_old_draft():
    row = queued()
    review_drafts.save(row.id, review_drafts.version(row), "draft", "manual_draft")
    version = review_drafts.version(review_store.get(row.id))
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[original("changed source")]), send_message=AsyncMock()
    )
    await review_service.decide(row.id, version, "approve", 111, client)
    assert review_drafts.get(row.id) is None
    assert review_store.get(row.id).preview == "changed source"
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_reply_saves_escaped_text_and_offers_all_actions():
    row = queued()
    context = SimpleNamespace(user_data={}, bot=SimpleNamespace(send_message=AsyncMock()))
    message = SimpleNamespace(reply_text=AsyncMock(return_value=SimpleNamespace(message_id=55)))
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(id=111),
    )
    await review_edit.begin(update, context, row, review_drafts.version(row))
    assert context.user_data["state"] == State.REVIEW_EDIT
    update.message = SimpleNamespace(
        text="<b>ویرایش</b>", reply_to_message=SimpleNamespace(message_id=55)
    )
    await review_edit.save(update, context)
    assert review_drafts.get(row.id).text == "&lt;b&gt;ویرایش&lt;/b&gt;"
    assert "review_edit" not in context.user_data
    markup = context.bot.send_message.call_args.kwargs["reply_markup"]
    actions = {
        b.callback_data.split(":")[1]
        for buttons in markup.inline_keyboard
        for b in buttons
        if b.callback_data
    }
    assert {"approve", "reject", "edit", "retry"} <= actions


def test_cancel_discards_editor_state_but_not_saved_draft():
    row = queued()
    review_drafts.save(row.id, review_drafts.version(row), "saved", "manual_draft")
    data = {"state": State.REVIEW_EDIT, "review_edit": (row.id, "token", 5)}
    reset(data)
    assert "review_edit" not in data
    assert review_drafts.get(row.id).text == "saved"


@pytest.mark.asyncio
async def test_ai_drop_after_referral_keeps_human_actions(monkeypatch):
    row = queued()
    save_ai_value("enabled", "true")
    monkeypatch.setattr(review_service, "rewrite_draft", AsyncMock(return_value=AI_DROP_RESULT))
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[original()]), send_message=AsyncMock()
    )
    await review_service.decide(row.id, review_drafts.version(row), "retry", 111, client)
    fresh = review_store.get(row.id)
    assert fresh.status == "pending"
    assert fresh.reason == "ai_rejected"
    _, markup = reviews.card(fresh)
    assert any(
        b.callback_data and ":edit:" in b.callback_data
        for buttons in markup.inline_keyboard
        for b in buttons
    )
    client.send_message.assert_not_awaited()


def test_late_notification_does_not_hide_new_edit():
    row = queued()
    old_version = review_drafts.version(row)
    review_drafts.save(row.id, old_version, "new", "manual_draft")
    review_store.mark_notified(row.id, 111, row.fingerprint, "pending", old_version)
    assert review_store.get(row.id).notified == "[]"


@pytest.mark.asyncio
async def test_manual_guard_block_edit_preserves_drop_identity_without_sending():
    row = review_store.enqueue(
        original(), -100123, -100456, None, "guard_block:THREAT:explicit threat"
    )
    version = review_drafts.version(row)
    assert review_drafts.save(row.id, version, "edited safe candidate", "manual_draft")

    fresh = review_store.get(row.id)
    assert fresh.reason == "guard_block:THREAT:explicit threat"
    assert review_drafts.get(row.id).text == "edited safe candidate"
    content, _ = reviews.card(fresh)
    assert content.startswith("🚫")
    assert "DROP" in content
