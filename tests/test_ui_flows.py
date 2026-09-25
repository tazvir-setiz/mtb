from html import unescape
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.database.database import get_session
from app.database.models import ChannelType
from app.database.repository import ChannelRepository
from app.handlers import dashboard, router, source, transfer
from app.handlers.callback_routes import CALLBACK_ROUTES
from app.handlers.states import (
    KEY_CURRENT_JOB_ID,
    KEY_PENDING_CHANNEL,
    KEY_PENDING_CHANNEL_KIND,
    State,
    reset,
)
from app.ui import keyboards, messages


def test_dashboard_disabled_button_has_no_action():
    payload = keyboards.main_menu(False, False).to_dict()
    disabled = [b for row in payload["inline_keyboard"] for b in row if "disabled" in b]
    assert len(disabled) == 1
    assert disabled[0]["disabled"] == {}
    assert "callback_data" not in disabled[0]
    assert keyboards.cancel_only(force_reply=True).to_dict()["force_reply"] is True


def test_dashboard_escapes_titles_and_explains_next_step():
    text = messages.dashboard("<source>", None, 12, ai_enabled=True)
    assert "&lt;source&gt;" in text
    assert "۲ از ۲" in text
    assert "پردازش هوشمند" in text


def test_reset_discards_drafts_but_preserves_job_controls():
    data = {"explicit_ids": [7], "range_end": 8, KEY_PENDING_CHANNEL: {}, KEY_CURRENT_JOB_ID: 3}
    reset(data)
    assert data == {KEY_CURRENT_JOB_ID: 3, "state": State.MAIN_MENU}


@pytest.mark.asyncio
async def test_range_flow_clears_previous_ids():
    data = {"explicit_ids": [7], "range_start": 1, "range_end": 8}
    reply = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply))
    )
    await transfer.start_range_flow(update, SimpleNamespace(user_data=data))
    assert data == {"state": State.RANGE_INPUT_START}
    assert reply.call_args.kwargs["reply_markup"].to_dict()["force_reply"] is True


@pytest.mark.asyncio
async def test_duplicate_transfer_confirmation_does_not_create_job(monkeypatch):
    def unexpected():
        pytest.fail("Duplicate confirmation reached transfer service")

    monkeypatch.setattr(transfer.transfer_service, "get_channels", unexpected)
    reply = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=reply))
    )
    await transfer.confirm_and_start(
        update, SimpleNamespace(user_data={"state": State.TRANSFERRING})
    )
    reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_is_saved_only_after_matching_confirmation(monkeypatch):
    info = SimpleNamespace(telegram_id=-100123, title="Channel", username="channel")
    monkeypatch.setattr(source, "ensure_started", AsyncMock())
    monkeypatch.setattr(source, "resolve_channel", AsyncMock(return_value=info))
    monkeypatch.setattr(dashboard, "show_dashboard", AsyncMock())
    reply = AsyncMock(return_value=SimpleNamespace(message_id=42))
    context = SimpleNamespace(user_data={KEY_PENDING_CHANNEL_KIND: "source"})
    update = SimpleNamespace(message=SimpleNamespace(text="@channel", reply_text=reply))
    await source.handle_channel_input(update, context)
    with get_session() as session:
        assert ChannelRepository.get_by_type(session, ChannelType.SOURCE) is None

    update.callback_query = SimpleNamespace(
        message=SimpleNamespace(message_id=41, reply_text=reply)
    )
    await source.handle_confirm(update, context, "source")
    with get_session() as session:
        assert ChannelRepository.get_by_type(session, ChannelType.SOURCE) is None

    update.callback_query.message.message_id = 42
    await source.handle_confirm(update, context, "source")
    with get_session() as session:
        assert ChannelRepository.get_by_type(session, ChannelType.SOURCE).telegram_id == -100123
    assert KEY_PENDING_CHANNEL not in context.user_data


@pytest.mark.asyncio
async def test_repeated_screen_refresh_is_not_an_error(monkeypatch):
    monkeypatch.setattr(router, "is_authorized", lambda _: True)
    monkeypatch.setitem(
        CALLBACK_ROUTES,
        ("menu", "stats"),
        AsyncMock(side_effect=BadRequest("Message is not modified")),
    )
    reply = AsyncMock()
    update = SimpleNamespace(
        callback_query=SimpleNamespace(data="menu:stats", answer=AsyncMock()),
        effective_message=SimpleNamespace(reply_text=reply),
    )
    await router.on_callback(update, SimpleNamespace())
    reply.assert_not_awaited()


def test_success_result_omits_retry_and_errors_fit_telegram_limit():
    callbacks = [
        b.callback_data for row in keyboards.result_menu(False).inline_keyboard for b in row
    ]
    assert "transfer:retry" not in callbacks
    assert "transfer:errors" not in callbacks
    text = messages.failed_messages_text([(i, "<" * 500) for i in range(1000)])
    assert len(unescape(text)) < 4096


@pytest.mark.asyncio
async def test_new_messages_opens_auto_forward_controls(monkeypatch):
    show = AsyncMock()
    monkeypatch.setattr(dashboard, "show_auto_forward", show)
    update, context = object(), object()
    await transfer.start_new_messages_flow(update, context)
    show.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_range_input_rejects_invalid_end_and_preserves_start(monkeypatch):
    monkeypatch.setattr(
        transfer.transfer_service, "get_channels", lambda: (1, 2, "Source", "Destination")
    )
    context = SimpleNamespace(user_data={"state": State.RANGE_INPUT_START})
    message = SimpleNamespace(text="10", reply_text=AsyncMock())
    update = SimpleNamespace(message=message)
    await transfer.handle_text_input(update, context, State.RANGE_INPUT_START)
    assert context.user_data["range_start"] == 10
    assert context.user_data["state"] == State.RANGE_INPUT_END
    message.text = "9"
    await transfer.handle_text_input(update, context, State.RANGE_INPUT_END)
    assert "range_end" not in context.user_data
    assert context.user_data["state"] == State.RANGE_INPUT_END
    message.text = "12"
    await transfer.handle_text_input(update, context, State.RANGE_INPUT_END)
    assert context.user_data["range_end"] == 12
    assert context.user_data["state"] == State.CONFIRM_TRANSFER


@pytest.mark.asyncio
async def test_id_input_keeps_only_selected_messages(monkeypatch):
    monkeypatch.setattr(
        transfer.transfer_service, "get_channels", lambda: (1, 2, "Source", "Destination")
    )
    context = SimpleNamespace(user_data={"state": State.IDS_INPUT})
    update = SimpleNamespace(message=SimpleNamespace(text="10,12", reply_text=AsyncMock()))
    await transfer.handle_text_input(update, context, State.IDS_INPUT)
    assert context.user_data["explicit_ids"] == [10, 12]
    assert context.user_data["state"] == State.CONFIRM_TRANSFER
