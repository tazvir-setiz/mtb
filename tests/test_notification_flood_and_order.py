from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.database.database import get_session
from app.database.models import ForwardJob, MessageStatus
from app.database.repository import ForwardedMessageRepository, ForwardJobRepository
from app.handlers import reviews
from app.services import review_store
from app.services.message_locks import channel_lock


def _make_msg(text="Sample message"):
    return SimpleNamespace(
        id=100,
        message=text,
        text=text,
        caption=None,
        entities=[],
        media=None,
    )


@pytest.mark.asyncio
async def test_systemic_ai_error_notifies_once_and_marks_all(monkeypatch):
    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[999]))

    # Enqueue 5 review requests all with invalid_credentials (systemic error)
    rows = []
    for i in range(5):
        m = _make_msg(f"Post {i}")
        m.id = 1000 + i
        r = review_store.enqueue(m, -1001, -1002, None, "invalid_credentials")
        rows.append(r)

    bot = SimpleNamespace(send_message=AsyncMock())
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(reviews.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await reviews.notify_pending(bot)

    # Exactly ONE systemic alert message must have been sent instead of 5!
    assert bot.send_message.await_count == 1
    call_args = bot.send_message.call_args[1]
    assert "خطای سراسری هوش مصنوعی" in call_args["text"]
    assert "کلید یا دسترسی حساب" in call_args["text"]

    # All 5 rows must now be marked as notified so they will never spam
    for r in rows:
        updated = review_store.get(r.id)
        assert 999 in json.loads(updated.notified)


@pytest.mark.asyncio
async def test_batch_notification_when_multiple_reviews_pending(monkeypatch):
    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[888]))

    # Enqueue 4 content reviews (non-systemic)
    rows = []
    for i in range(4):
        m = _make_msg(f"Ad text {i}")
        m.id = 2000 + i
        r = review_store.enqueue(m, -1001, -1002, None, "spam")
        rows.append(r)

    bot = SimpleNamespace(send_message=AsyncMock())
    sleeps = 0

    async def sleep(_):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(reviews.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await reviews.notify_pending(bot)

    # Exactly ONE batch notification message must be sent instead of 4 individual cards!
    assert bot.send_message.await_count == 1
    call_args = bot.send_message.call_args[1]
    assert "پیام جدید در صف بازبینی قرار گرفت" in call_args["text"]
    assert "اسپم" in call_args["text"]

    # All 4 rows must be marked as notified
    for r in rows:
        updated = review_store.get(r.id)
        assert 888 in json.loads(updated.notified)


@pytest.mark.asyncio
async def test_channel_lock_preserves_sequential_order():
    order = []

    async def worker(task_id: int, delay: float):
        async with channel_lock(-10099):
            await asyncio.sleep(delay)
            order.append(task_id)

    # Launch task 1 first (with 0.05s delay) and task 2 second (with 0.01s delay)
    # Without channel_lock, task 2 would finish before task 1.
    # With channel_lock, task 1 must finish before task 2 starts!
    t1 = asyncio.create_task(worker(1, 0.05))
    await asyncio.sleep(0.005)
    t2 = asyncio.create_task(worker(2, 0.01))

    await asyncio.gather(t1, t2)
    assert order == [1, 2]
