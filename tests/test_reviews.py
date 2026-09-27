import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.database import get_session
from app.database.models import MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository
from app.handlers import reviews
from app.services import review_drafts, review_service, review_store
from app.services.ai_policy import AIReviewRequired
from app.services.ai_settings import save_ai_value
from app.services.ai_transport import AIRequestError
from app.services.review_service import decide
from app.telegram import message_sender
from app.telegram.forward_service import forward_range


def message(text="متن برای بررسی https://example.com"):
    return SimpleNamespace(id=7, message=text, entities=[], media=None, poll=None)


def queued(original=None):
    return review_store.enqueue(original or message(), -100123, -100456, None, "review")


@pytest.mark.asyncio
async def test_review_is_saved_and_deduplicated_before_forwarding(monkeypatch):
    guard = AsyncMock(side_effect=AIReviewRequired("low_confidence"))
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", guard)
    client = SimpleNamespace(send_message=AsyncMock())
    for _ in range(2):
        with pytest.raises(AIReviewRequired):
            await message_sender.send_message(client, message(), -100123, -100456, None)
    assert len(review_store.pending()) == 1
    assert review_store.pending()[0].reason == "low_confidence"
    guard.assert_awaited_once()
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_sanitizes_and_does_not_recheck_ai_or_send_twice(monkeypatch):
    original = message()
    row = queued(original)
    guard = AsyncMock(side_effect=AssertionError("AI must not run again"))
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", guard)
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[original]),
        send_message=AsyncMock(return_value=SimpleNamespace(id=88)),
    )
    for _ in range(2):
        await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    client.send_message.assert_awaited_once()
    assert client.send_message.call_args.kwargs["entity"] == -100456
    assert "https://" not in client.send_message.call_args.kwargs["message"]
    assert review_store.get(row.id).status == "sent"
    guard.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejection_prevents_later_retry(monkeypatch):
    row = queued()
    await decide(row.id, row.fingerprint[:12], "reject", 111, None)
    guard = AsyncMock()
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", guard)
    assert await message_sender.send_message(None, message(), -100123, -100456, None) is None
    guard.assert_not_awaited()
    assert review_store.get(row.id).status == "rejected"


@pytest.mark.asyncio
async def test_edited_source_invalidates_old_approval():
    row = queued()
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message("edited content")]), send_message=AsyncMock()
    )
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    refreshed = review_store.get(row.id)
    assert refreshed.status == "pending"
    assert refreshed.fingerprint != row.fingerprint
    assert refreshed.notified == "[]"
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_admins_cannot_send_same_review_concurrently():
    row = queued()
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def send(**kwargs):
        entered.set()
        await finish.wait()
        return SimpleNamespace(id=88)

    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message()]), send_message=AsyncMock(side_effect=send)
    )
    first = asyncio.create_task(decide(row.id, row.fingerprint[:12], "approve", 111, client))
    await entered.wait()
    await decide(row.id, row.fingerprint[:12], "approve", 222, client)
    finish.set()
    await first
    client.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_uncertain_send_needs_explicit_reset():
    row = queued()
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message()]),
        send_message=AsyncMock(side_effect=TimeoutError),
    )
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    assert review_store.get(row.id).status == "uncertain"
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    client.send_message.assert_awaited_once()
    await decide(row.id, row.fingerprint[:12], "reset", 111, None)
    assert review_store.get(row.id).status == "pending"


def test_restart_recovers_inflight_without_automatically_sending():
    row = queued()
    review_store.mark_notified(row.id, 111)
    assert review_store.claim(row.id, 111)
    review_store.recover_interrupted()
    recovered = review_store.get(row.id)
    assert recovered.status == "uncertain"
    assert recovered.notified == "[]"
    assert not review_store.claim(row.id, 222)


def test_old_notification_cannot_mark_new_content_delivered():
    old = queued()
    updated = review_store.enqueue(
        message("new content"), -100123, -100456, None, "content_changed"
    )
    review_store.mark_notified(old.id, 111, old.fingerprint, old.status)
    assert review_store.get(updated.id).notified == "[]"


def test_media_identity_changes_invalidate_approval_but_file_reference_does_not():
    original = message()
    data = {"id": 1, "file_reference": "old"}
    original.media = SimpleNamespace(to_dict=lambda: data.copy())
    first = review_store.content_fingerprint(original)
    data["file_reference"] = "refreshed"
    assert review_store.content_fingerprint(original) == first
    data["id"] = 2
    assert review_store.content_fingerprint(original) != first


@pytest.mark.parametrize("text", ["<b>" * 2000, "😀" * 2500, "&" * 2500])
def test_card_escapes_content_and_stays_within_telegram_limit(text):
    row = queued(message(text))
    content, markup = reviews.card(row)
    assert len(content.encode("utf-16-le")) // 2 < 4096
    assert "<b>" not in content
    for buttons in markup.inline_keyboard:
        for button in buttons:
            assert not button.callback_data or len(button.callback_data.encode()) <= 64


@pytest.mark.asyncio
async def test_non_admin_cannot_approve(monkeypatch):
    decision = AsyncMock()
    monkeypatch.setattr(reviews, "decide", decision)
    query = SimpleNamespace(data="review:approve:1:abc", answer=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=999), callback_query=query)
    await reviews.on_callback(update, SimpleNamespace())
    decision.assert_not_awaited()
    assert query.answer.call_args.kwargs["show_alert"]


@pytest.mark.asyncio
async def test_notification_is_persisted_and_not_repeated(monkeypatch):
    row = queued()
    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[111]))
    bot = SimpleNamespace(send_message=AsyncMock())
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(reviews.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await reviews.notify_pending(bot)
    bot.send_message.assert_awaited_once()
    assert json.loads(review_store.get(row.id).notified) == [111]


@pytest.mark.asyncio
async def test_review_resolution_updates_failed_record_and_job():
    original = message()
    with get_session() as session:
        job = ForwardJobRepository.create(session, -100123, -100456, 7, 7, 1)
        job.failed_messages = 1
        job_id = job.id
        ForwardedMessageRepository.record(
            session, job_id, -100123, 7, -100456, MessageStatus.FAILED
        )
    row = review_store.enqueue(original, -100123, -100456, job_id, "review")
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[original]),
        send_message=AsyncMock(return_value=SimpleNamespace(id=88)),
    )
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        assert job.failed_messages == 0
        assert job.successful_messages == 1
        assert ForwardedMessageRepository.exists(session, -100123, 7, -100456)


@pytest.mark.asyncio
async def test_manual_forward_preserves_job_for_review(monkeypatch):
    with get_session() as session:
        job = ForwardJobRepository.create(session, -100123, -100456, 7, 7, 1)
        job_id = job.id
    monkeypatch.setattr(
        message_sender, "apply_ai_guardrails", AsyncMock(side_effect=AIReviewRequired("review"))
    )
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message()]), send_message=AsyncMock()
    )
    await forward_range(client, job_id, -100123, -100456, [7])
    row = review_store.pending()[0]
    assert row.job_id == job_id
    assert row.destination_id == -100456
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_notification_is_retried_not_marked_delivered(monkeypatch):
    row = queued()
    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[111]))
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=[OSError("offline"), None]))
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            assert review_store.get(row.id).notified == "[]"
        if sleeps > 5:
            raise asyncio.CancelledError

    monkeypatch.setattr(reviews.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await reviews.notify_pending(bot)
    assert bot.send_message.await_count == 2
    assert json.loads(review_store.get(row.id).notified) == [111]


@pytest.mark.asyncio
async def test_ai_retry_rewrites_instead_of_bypassing_guard(monkeypatch):
    save_ai_value("enabled", "true")
    row = queued()
    guard = AsyncMock(return_value="متن بازنویسی شده")
    monkeypatch.setattr(review_service, "rewrite_draft", guard)
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message()]),
        send_message=AsyncMock(return_value=SimpleNamespace(id=90)),
    )
    await decide(row.id, row.fingerprint[:12], "retry", 111, client)
    guard.assert_awaited_once()
    client.send_message.assert_not_awaited()
    assert review_store.get(row.id).status == "pending"
    assert review_drafts.get(row.id).text == "متن بازنویسی شده"
    await decide(row.id, row.fingerprint[:12], "approve", 111, client)
    client.send_message.assert_not_awaited()
    await decide(row.id, review_drafts.version(review_store.get(row.id)), "approve", 111, client)
    assert client.send_message.call_args.kwargs["message"] == "متن بازنویسی شده"
    assert review_store.get(row.id).status == "sent"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [AIReviewRequired("timeout"), AIRequestError("timeout")])
async def test_ai_retry_failure_stays_pending_with_exact_reason(monkeypatch, error):
    save_ai_value("enabled", "true")
    row = queued()
    monkeypatch.setattr(
        review_service, "rewrite_draft", AsyncMock(side_effect=error)
    )
    client = SimpleNamespace(
        get_messages=AsyncMock(return_value=[message()]), send_message=AsyncMock()
    )
    await decide(row.id, row.fingerprint[:12], "retry", 111, client)
    assert review_store.get(row.id).status == "pending"
    assert review_store.get(row.id).reason == "timeout"
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_retry_cannot_send_raw_text_when_ai_disabled():
    row = queued()
    client = SimpleNamespace(get_messages=AsyncMock(), send_message=AsyncMock())
    await decide(row.id, row.fingerprint[:12], "retry", 111, client)
    client.get_messages.assert_not_awaited()
    client.send_message.assert_not_awaited()
    assert review_store.get(row.id).status == "pending"
