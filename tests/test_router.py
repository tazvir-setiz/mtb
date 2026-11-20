import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.handlers import router
from app.handlers.callback_routes import CALLBACK_ROUTES
from app.handlers.states import State, get_state, set_state
from app.services.guard_profile import default_profile
from app.ui import keyboards
from app.ui.buttons.channels import channel_management
from app.ui.buttons.guard import guard_confirm, guard_menu
from app.ui.buttons.transfer import destination_selection, source_selection
from app.ui.callbacks import parse


def test_every_button_has_a_callable_route():
    channel = SimpleNamespace(title="Channel", telegram_id=-1001)
    menus = [
        source_selection([channel] * 11),
        destination_selection([channel] * 11, [-1001]),
        channel_management("source", [channel]),
        channel_management("destination", [channel]),
        channel_management("source", [channel], removing=True),
        channel_management("destination", [channel], removing=True),
        guard_menu(default_profile()),
        guard_confirm("test-token"),
        keyboards.main_menu(True, True, True, -1001, -1002),
        keyboards.main_menu(False, False),
        keyboards.channel_confirm("source"),
        keyboards.channel_confirm("destination"),
    ]
    for name, builder in vars(keyboards).items():
        if inspect.isfunction(builder) and not name.startswith("_"):
            if all(
                p.default is not p.empty for p in inspect.signature(builder).parameters.values()
            ):
                menus.append(builder())

    used_routes = set()
    for menu in menus:
        for row in menu.inline_keyboard:
            for button in row:
                if button.callback_data:
                    namespace, action, _ = parse(button.callback_data)
                    key = (namespace, action)
                    handler = CALLBACK_ROUTES[key]
                    inspect.signature(handler).bind(object(), object())
                    used_routes.add(key)
    assert used_routes == set(CALLBACK_ROUTES)


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized", [False, True])
async def test_callback_authorization_and_dispatch(monkeypatch, authorized):
    handler = AsyncMock()
    monkeypatch.setitem(CALLBACK_ROUTES, ("menu", "stats"), handler)
    monkeypatch.setattr(router, "is_authorized", lambda _: authorized)
    query = SimpleNamespace(data="menu:stats", answer=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace()
    await router.on_callback(update, context)
    query.answer.assert_awaited_once()
    if authorized:
        handler.assert_awaited_once_with(update, context)
    else:
        handler.assert_not_awaited()
        assert query.answer.call_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_unknown_callback_is_acknowledged(monkeypatch):
    monkeypatch.setattr(router, "is_authorized", lambda _: True)
    query = SimpleNamespace(data="unknown:action", answer=AsyncMock())
    await router.on_callback(SimpleNamespace(callback_query=query), SimpleNamespace())
    query.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_handler_toast_wins_and_router_does_not_answer_twice(monkeypatch):
    from app.telegram.callback_ack import ack

    async def handler(update, context):
        await ack(update.callback_query, "به‌روز شد")

    monkeypatch.setitem(CALLBACK_ROUTES, ("menu", "refresh"), handler)
    monkeypatch.setattr(router, "is_authorized", lambda _: True)
    query = SimpleNamespace(id="router-ack-1", data="menu:refresh", answer=AsyncMock())

    await router.on_callback(SimpleNamespace(callback_query=query), SimpleNamespace())

    query.answer.assert_awaited_once_with("به‌روز شد", show_alert=False)


@pytest.mark.asyncio
async def test_stale_callback_query_error_is_not_reported_to_the_user(monkeypatch):
    async def handler(update, context):
        raise BadRequest(
            "Query is too old and response timeout expired or query id is invalid"
        )

    monkeypatch.setitem(CALLBACK_ROUTES, ("menu", "refresh"), handler)
    monkeypatch.setattr(router, "is_authorized", lambda _: True)
    reply = AsyncMock()
    query = SimpleNamespace(id="router-ack-2", data="menu:refresh", answer=AsyncMock())
    update = SimpleNamespace(
        callback_query=query,
        effective_message=SimpleNamespace(reply_text=reply),
    )

    await router.on_callback(update, SimpleNamespace())

    reply.assert_not_awaited()
    query.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_signature_input_is_saved_and_state_reset(monkeypatch):
    monkeypatch.setattr(router, "is_authorized", lambda _: True)
    show_settings = AsyncMock()
    monkeypatch.setattr(router.settings_handlers, "show_settings", show_settings)
    context = SimpleNamespace(user_data={})
    set_state(context.user_data, State.SIGNATURE_INPUT)
    update = SimpleNamespace(
        message=SimpleNamespace(text_html="<b>signature</b>", reply_text=AsyncMock())
    )
    await router.on_text(update, context)
    with get_session() as session:
        assert SettingsRepository.get(session, "signature_text") == "<b>signature</b>"
    assert get_state(context.user_data) != State.SIGNATURE_INPUT
    show_settings.assert_awaited_once_with(update, context)
