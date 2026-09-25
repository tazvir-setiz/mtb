from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.database.database import get_session
from app.database.repository import SettingsRepository
from app.handlers import username_settings
from app.handlers.states import State
from app.services import ai_service
from app.services.ai_policy import (
    DROP_CATEGORIES,
    REVIEW_CATEGORIES,
    AIProcessingError,
    AIReviewRequired,
    parse_decision,
)
from app.services.text_sanitizer import USERNAME_SETTING, sanitize_text
from app.telegram import message_sender
from app.telegram.forward_errors import ForwardErrorType, classify_error


@pytest.mark.parametrize("category", DROP_CATEGORIES)
def test_drop_categories_never_publish_body(category):
    assert parse_decision(f"[{category}] unsafe body") == "__DROP__"


@pytest.mark.parametrize("category", REVIEW_CATEGORIES)
def test_review_is_not_published(category):
    with pytest.raises(AIReviewRequired):
        parse_decision(f"[{category}] body")


@pytest.mark.parametrize(
    "result",
    [
        None,
        "hello",
        "[unknown] body",
        "[تایید شده]",
        "```[تایید شده] body```",
        "[تایید شده] [نیازمند بررسی] body",
    ],
)
def test_invalid_decision_blocks_publication(result):
    with pytest.raises(AIProcessingError):
        parse_decision(result)


def test_drop_word_in_approved_text_is_not_a_drop_decision():
    assert parse_decision("[تایید شده] DROP TABLE is SQL") == "DROP TABLE is SQL"


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["http_error", "network", "invalid_json", "review", "approved"])
async def test_ai_response_contract(monkeypatch, outcome):
    monkeypatch.setattr(
        ai_service,
        "settings",
        replace(ai_service.settings, ai_enabled=True, ai_api_key="test-only"),
    )
    response = httpx.Response(
        503 if outcome == "http_error" else 200,
        request=httpx.Request("POST", "https://example.test"),
        json={
            "choices": [
                {
                    "message": {
                        "content": "[نیازمند بررسی]" if outcome == "review" else "[تایید شده] safe"
                    }
                }
            ]
        },
    )
    if outcome == "invalid_json":
        response = httpx.Response(200, request=response.request, content=b"invalid json")
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    if outcome == "network":
        client.post.side_effect = httpx.ConnectError("offline")
    manager = AsyncMock()
    manager.__aenter__.return_value = client
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **_: manager)
    if outcome == "approved":
        assert await ai_service.apply_ai_guardrails("original") == "safe"
    else:
        with pytest.raises(AIReviewRequired if outcome == "review" else AIProcessingError):
            await ai_service.apply_ai_guardrails("original")
    payload = client.post.call_args.kwargs["json"]
    assert payload["messages"][1] == {"role": "user", "content": "original"}


def test_username_sanitization_and_hidden_links():
    original = (
        '<b>@source_name</b> contact person@example.com <a href="https://example.com">label</a>'
    )
    assert sanitize_text(original, remove_links=True) == "<b></b> contact person@example.com label"
    with get_session() as session:
        SettingsRepository.set(session, USERNAME_SETTING, "@MyDestination")
    assert (
        sanitize_text(original, remove_links=True)
        == "<b>@MyDestination</b> contact person@example.com label"
    )
    assert (
        sanitize_text("[label](https://example.com) https://example.com", remove_links=True)
        == "label"
    )


@pytest.mark.asyncio
async def test_username_setting_is_saved_validated_and_deleted():
    context = SimpleNamespace(user_data={"state": State.USERNAME_INPUT})
    message = SimpleNamespace(text="bad name", reply_text=AsyncMock())
    update = SimpleNamespace(message=message, effective_message=message, callback_query=None)
    await username_settings.save(update, context)
    assert context.user_data["state"] == State.USERNAME_INPUT
    message.text = "MyDestination"
    await username_settings.save(update, context)
    with get_session() as session:
        assert SettingsRepository.get(session, USERNAME_SETTING) == "@MyDestination"
    assert sanitize_text("@other_name", remove_links=False) == "@MyDestination"
    await username_settings.remove(update, context)
    assert sanitize_text("@other_name", remove_links=False) == ""


@pytest.mark.asyncio
async def test_poll_cannot_bypass_enabled_moderation(monkeypatch):
    monkeypatch.setattr(
        message_sender, "settings", replace(message_sender.settings, ai_enabled=True)
    )
    client = SimpleNamespace(forward_messages=AsyncMock())
    with pytest.raises(AIReviewRequired):
        await message_sender.send_message(client, SimpleNamespace(poll=object()), 1, 2, None)
    client.forward_messages.assert_not_awaited()


def test_moderation_errors_have_actionable_categories():
    assert classify_error(AIReviewRequired()) == ForwardErrorType.AI_REVIEW
    assert classify_error(AIProcessingError()) == ForwardErrorType.AI_ERROR
