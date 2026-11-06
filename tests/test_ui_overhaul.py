import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.handlers.callback_routes import CALLBACK_ROUTES
from app.services.statistics_service import get_recent_messages, get_statistics_text, get_system_health_report
from app.ui import keyboards, messages


def test_main_menu_markup_structure_and_refresh():
    # Ready state
    markup = keyboards.main_menu(
        source_ready=True,
        destination_ready=True,
        auto_forward_enabled=True,
        pending_reviews=3,
    )
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]
    assert "system:health" in callbacks
    assert "menu:refresh" in callbacks
    assert "menu:stats" in callbacks
    assert "menu:recent" in callbacks
    assert "menu:reviews" in callbacks

    # Check review button has count badge
    review_button = next(
        b for row in markup.inline_keyboard for b in row if b.callback_data == "menu:reviews"
    )
    assert "(3)" in review_button.text


def test_dashboard_text_with_metadata():
    text = messages.dashboard(
        source_title="SourceChannel",
        destination_title="DestChannel",
        total_forwarded=150,
        auto_forward_enabled=True,
        ai_enabled=True,
        signature_enabled=True,
        pending_reviews=4,
        ai_model="gemini-2.5-flash",
    )
    assert "SourceChannel" in text
    assert "DestChannel" in text
    assert "150" in text
    assert "پردازش هوشمند" in text
    assert "gemini-2.5-flash" in text
    assert "۴" in text or "4" in text


def test_statistics_rich_text_breakdown():
    text = messages.statistics_text(
        total=100,
        success=85,
        failed=5,
        duplicate=10,
        source_title="مبداها: 1",
        destination_title="مقصدها: 2",
        last_operation="1405-08-15 10:00",
        pending_reviews=2,
        rejected_reviews=7,
        approved_reviews=12,
        auto_stats={"received": 50, "sent": 45, "waiting": 0},
    )
    assert "100" in text
    assert "85" in text
    assert "85.0%" in text
    assert "7" in text or "۷" in text
    assert "12" in text or "۱۲" in text
    assert "در صف بررسی" in text
    assert "Auto-Forward" in text or "سشن زنده" in text


def test_recent_messages_rich_feed():
    rich_items = [
        {
            "icon": "✅",
            "source": "کانال خبر",
            "destination": "کانال آرشیو",
            "message_id": 1234,
            "time": "۱۰:۳۰",
            "status_text": "ارسال شد",
            "preview": "متن تستی خبر مهم روز...",
            "reason": None,
        },
        {
            "icon": "🚫",
            "source": "کانال خبر",
            "destination": "کانال آرشیو",
            "message_id": 1235,
            "time": "۱۰:۳۵",
            "status_text": "مسدود شده توسط گارد",
            "preview": "متن توهین‌آمیز فیلتر شده",
            "reason": "گارد پیام را توهین مستقیم تشخیص داده است",
        },
    ]
    text = messages.recent_messages_text(rich_items)
    assert "کانال خبر ➔ کانال آرشیو" in text
    assert "متن تستی خبر مهم روز" in text
    assert "مسدود شده توسط گارد" in text
    assert "گارد پیام را توهین مستقیم تشخیص داده است" in text

    # Backward compatibility with legacy (id, icon) tuples
    legacy_items = [("123/45 → 678", "✅")]
    legacy_text = messages.recent_messages_text(legacy_items)
    assert "#123/45 → 678" in legacy_text


@pytest.mark.asyncio
async def test_system_health_report_generation(monkeypatch):
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    mock_client.is_user_authorized = AsyncMock(return_value=True)
    mock_me = MagicMock()
    mock_me.first_name = "ForwarderUser"
    mock_me.username = "forwarder_bot_user"
    mock_me.id = 123456789
    mock_client.get_me = AsyncMock(return_value=mock_me)

    monkeypatch.setattr("app.services.statistics_service.get_client", lambda: mock_client)

    report = await get_system_health_report()
    assert "سلامت سیستم" in report
    assert "ForwarderUser" in report or "123456789" in report
    assert "پایگاه داده" in report
    assert "هوش مصنوعی" in report


def test_callback_routes_health_and_refresh():
    assert ("system", "health") in CALLBACK_ROUTES
    assert ("menu", "refresh") in CALLBACK_ROUTES


@pytest.mark.asyncio
async def test_review_actions_update_in_place_without_spam(monkeypatch):
    from app.handlers import reviews
    from app.services import review_store

    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[111], is_admin=lambda x: x == 111))

    original = SimpleNamespace(id=50, message="متن تست برای بازنویسی", entities=[], media=None, poll=None)
    row = review_store.enqueue(original, -100111, -100222, None, "abuse")

    monkeypatch.setattr(reviews, "decide", AsyncMock(return_value="بازنگری آماده است؛ پس از مشاهده، تأیید کنید."))
    monkeypatch.setattr(reviews, "ensure_started", AsyncMock())

    edit_mock = AsyncMock()
    reply_mock = AsyncMock()
    query = SimpleNamespace(
        data=f"review:retry:{row.id}:abc",
        answer=AsyncMock(),
        message=SimpleNamespace(message_id=99),
        edit_message_text=edit_mock,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=111),
        effective_chat=SimpleNamespace(type="private", id=111),
        effective_message=SimpleNamespace(reply_text=reply_mock),
        callback_query=query,
    )

    await reviews.on_callback(update, SimpleNamespace())

    edit_mock.assert_awaited_once()
    reply_mock.assert_not_awaited()
    assert "بازنگری آماده است" in edit_mock.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_review_approve_updates_in_place_without_spam(monkeypatch):
    from app.handlers import reviews
    from app.services import review_store

    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[111], is_admin=lambda x: x == 111))
    original = SimpleNamespace(id=51, message="پیام تایید", entities=[], media=None, poll=None)
    row = review_store.enqueue(original, -100111, -100222, None, "review")

    monkeypatch.setattr(reviews, "decide", AsyncMock(return_value="پیام با تأیید شما ارسال شد."))
    monkeypatch.setattr(reviews, "ensure_started", AsyncMock())

    edit_mock = AsyncMock()
    reply_mock = AsyncMock()
    query = SimpleNamespace(
        data=f"review:approve:{row.id}:abc",
        answer=AsyncMock(),
        message=SimpleNamespace(message_id=100),
        edit_message_text=edit_mock,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=111),
        effective_chat=SimpleNamespace(type="private", id=111),
        effective_message=SimpleNamespace(reply_text=reply_mock),
        callback_query=query,
    )

    await reviews.on_callback(update, SimpleNamespace())

    edit_mock.assert_awaited_once()
    reply_mock.assert_not_awaited()
    assert "تأیید شد" in edit_mock.call_args.kwargs["text"]


@pytest.mark.asyncio
async def test_review_preview_toggles_in_place(monkeypatch):
    from app.handlers import reviews
    from app.services import review_store

    monkeypatch.setattr(reviews, "settings", SimpleNamespace(admin_ids=[111], is_admin=lambda x: x == 111))
    original = SimpleNamespace(id=52, message="متن مخفی پیام آزمایشی", entities=[], media=None, poll=None)
    row = review_store.enqueue(original, -100111, -100222, None, "review")

    edit_mock = AsyncMock()
    reply_mock = AsyncMock()
    query = SimpleNamespace(
        data=f"review:preview:{row.id}:abc",
        answer=AsyncMock(),
        message=SimpleNamespace(message_id=101),
        edit_message_text=edit_mock,
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=111),
        effective_chat=SimpleNamespace(type="private", id=111),
        effective_message=SimpleNamespace(reply_text=reply_mock),
        callback_query=query,
    )

    await reviews.on_callback(update, SimpleNamespace())

    edit_mock.assert_awaited_once()
    reply_mock.assert_not_awaited()
    assert "متن مخفی پیام آزمایشی" in edit_mock.call_args.kwargs["text"]
