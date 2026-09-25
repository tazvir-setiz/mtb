from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon.errors import MessageIdInvalidError
from telethon.tl.types import MessageMediaWebPage

from app.telegram import message_sender


def make_message(**changes):
    values = dict(id=7, message="original", entities=[], media=None, poll=None)
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "processed, expected",
    [
        ("<b>edited</b>", "<b>edited</b>\n\n<i>signature</i>"),
        ("", "<i>signature</i>"),
    ],
)
async def test_processed_html_and_signature(monkeypatch, processed, expected):
    ai = AsyncMock(return_value=processed)
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", ai)
    client = SimpleNamespace(send_message=AsyncMock())
    media = object()
    await message_sender.send_message(
        client, make_message(media=media), -1001, -1002, "<i>signature</i>"
    )
    ai.assert_awaited_once_with("original")
    client.send_message.assert_awaited_once_with(
        entity=-1002, message=expected, file=media, parse_mode="html", link_preview=False
    )


@pytest.mark.asyncio
async def test_ai_rejection_does_not_send(monkeypatch):
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", AsyncMock(return_value="__DROP__"))
    client = SimpleNamespace(send_message=AsyncMock())
    result = await message_sender.send_message(client, make_message(), -1001, -1002, "sig")
    assert result is None
    client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_bypasses_ai(monkeypatch):
    ai = AsyncMock()
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", ai)
    sent = SimpleNamespace(id=99)
    client = SimpleNamespace(forward_messages=AsyncMock(return_value=[sent]))
    result = await message_sender.send_message(
        client, make_message(poll=object()), -1001, -1002, "sig"
    )
    assert result is sent
    ai.assert_not_awaited()
    client.forward_messages.assert_awaited_once_with(
        entity=-1002, messages=7, from_peer=-1001, drop_author=True
    )


@pytest.mark.asyncio
async def test_web_preview_not_uploaded(monkeypatch):
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", AsyncMock(return_value="text"))
    client = SimpleNamespace(send_message=AsyncMock())
    await message_sender.send_message(
        client, make_message(media=MessageMediaWebPage(webpage=None)), -1001, -1002, None
    )
    assert client.send_message.call_args.kwargs["file"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("messages", [[], [None]])
async def test_missing_message(messages):
    client = SimpleNamespace(get_messages=AsyncMock(return_value=messages))
    with pytest.raises(MessageIdInvalidError):
        await message_sender.fetch_and_send_message(client, 7, -1001, -1002, None)
