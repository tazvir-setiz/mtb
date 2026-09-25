from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from telegram.error import BadRequest

from app.config import settings
from app.handlers import ai_settings as handlers
from app.handlers.states import State
from app.services import ai_service
from app.services.ai_settings import load_ai_settings, save_ai_value, validate_ai_value


def make_update(text="", user_id=111, chat_type="private"):
    message = SimpleNamespace(text=text, reply_text=AsyncMock(), delete=AsyncMock())
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(type=chat_type),
        effective_message=message,
        message=message,
        callback_query=None,
    )


def test_database_overrides_environment_and_clear_does_not_restore_old_key():
    defaults = replace(settings, ai_enabled=True, ai_api_key="old-key", ai_model="old-model")
    assert load_ai_settings(defaults).api_key == "old-key"
    save_ai_value("model", "new-model")
    save_ai_value("api_key", "new-key")
    assert load_ai_settings(defaults).model == "new-model"
    assert load_ai_settings(defaults).api_key == "new-key"
    assert "new-key" not in repr(load_ai_settings(defaults))
    save_ai_value("api_key", "")
    assert load_ai_settings(defaults).api_key == ""
    assert not load_ai_settings(defaults).enabled


def test_changing_provider_clears_key_and_disables_ai():
    save_ai_value("api_key", "secret")
    save_ai_value("enabled", "true")
    save_ai_value("base_url", "https://new-provider.example/v1/chat/completions")
    config = load_ai_settings()
    assert config.api_key == ""
    assert not config.enabled


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com?key=secret",
        "[https://example.com](https://example.com)",
        "https://example.com:invalid",
        "",
    ],
)
def test_invalid_service_url_is_rejected(value):
    assert validate_ai_value("base_url", value)


@pytest.mark.asyncio
async def test_key_saved_privately_deleted_and_never_echoed():
    update = make_update("private-api-secret")
    context = SimpleNamespace(user_data={"state": State.AI_KEY_INPUT})
    await handlers.save(update, context)
    assert load_ai_settings().api_key == "private-api-secret"
    update.message.delete.assert_awaited_once()
    assert "private-api-secret" not in str(update.message.reply_text.call_args_list)
    assert context.user_data["state"] == State.MAIN_MENU


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,chat_type", [(999, "private"), (111, "group")])
async def test_non_admin_and_group_cannot_change_ai(user_id, chat_type):
    save_ai_value("api_key", "original")
    update = make_update("replacement", user_id, chat_type)
    context = SimpleNamespace(user_data={"state": State.AI_KEY_INPUT})
    await handlers.save(update, context)
    await handlers.toggle(update, context)
    await handlers.clear_key(update, context)
    assert load_ai_settings().api_key == "original"


@pytest.mark.asyncio
async def test_deletion_failure_does_not_echo_key_or_prevent_save():
    update = make_update("private-api-secret")
    update.message.delete.side_effect = BadRequest("cannot delete")
    await handlers.save(update, SimpleNamespace(user_data={"state": State.AI_KEY_INPUT}))
    assert load_ai_settings().api_key == "private-api-secret"
    assert "private-api-secret" not in str(update.message.reply_text.call_args_list)


@pytest.mark.asyncio
async def test_enable_requires_key_and_persists_toggle():
    save_ai_value("api_key", "")
    update = make_update()
    context = SimpleNamespace(user_data={})
    await handlers.toggle(update, context)
    assert not load_ai_settings().enabled
    save_ai_value("base_url", "https://example.test/v1/chat/completions")
    save_ai_value("model", "test-model")
    save_ai_value("api_key", "test-key")
    await handlers.toggle(update, context)
    assert load_ai_settings().enabled
    await handlers.toggle(update, context)
    assert not load_ai_settings().enabled


@pytest.mark.asyncio
async def test_next_ai_request_uses_saved_provider_model_and_key(monkeypatch):
    save_ai_value("base_url", "https://example.test/v1/chat/completions")
    save_ai_value("model", "custom-model")
    save_ai_value("api_key", "test-key")
    save_ai_value("enabled", "true")
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://example.test"),
        json={"choices": [{"message": {"content": "[تایید شده] safe"}}]},
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_: manager)
    assert await ai_service.apply_ai_guardrails("text") == "safe"
    call = client.post.call_args
    assert call.args == ("https://example.test/v1/chat/completions",)
    assert call.kwargs["json"]["model"] == "custom-model"
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
    save_ai_value("enabled", "false")
    assert await ai_service.apply_ai_guardrails("original") == "original"
    assert client.post.await_count == 1
