from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest

from app import config
from app.telegram import channel_service
from app.telegram.bale_bot import BaleBot
from app.telegram.bale_format import to_bale_markdown
from app.telegram.channel_service import (
    ChannelAccessError,
    normalize_channel_ref,
    resolve_channel,
)
from app.telegram.client import BotClient


# --------------------------------------------------------------------------
# HTML -> Bale Markdown
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<b>سلام</b>", " *سلام* "),
        ("📥 <b>کانال مبدأ</b>", "📥 *کانال مبدأ* "),
        ("<i>متن کج</i> بعد", " _متن کج_ بعد"),
        ("<code>-1001234567890</code>", "`-1001234567890`"),
        ('<a href="https://docs.bale.ai">مستندات</a>', "[مستندات](https://docs.bale.ai)"),
        ("<pre>line1\nline2</pre>", "```\nline1\nline2\n```"),
        ("<u>underline</u>", "underline"),
        ("<blockquote>نقل قول</blockquote>", "نقل قول"),
        ("<tg-spoiler>مخفی</tg-spoiler>", "مخفی"),
        ("a &amp; b &lt; c", "a & b < c"),
        ("<b><i>bold italic</i></b>", " * _bold italic_ * "),
    ],
)
def test_html_is_converted_to_bale_markdown(html, expected):
    assert to_bale_markdown(html) == expected


def test_no_raw_html_tags_survive_conversion():
    html = (
        "<b>کانال مبدأ</b>\n"
        "<blockquote><code>@channel_username</code>\n"
        "<code>-1001234567890</code></blockquote>\n"
        "<i>راهنما</i> و <u>خط</u> و <s>حذف</s> و <a href='https://x.y'>لینک</a>"
    )
    converted = to_bale_markdown(html)
    assert "<" not in converted and ">" not in converted
    assert "*کانال مبدأ*" in converted
    assert "`@channel_username`" in converted
    assert "[لینک](https://x.y)" in converted


def test_plain_text_is_unchanged():
    assert to_bale_markdown("سلام دنیا") == "سلام دنیا"


# --------------------------------------------------------------------------
# BaleBot: every outgoing HTML payload is rewritten, parse_mode is dropped
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bale_bot_rewrites_html_payload(monkeypatch):
    captured: list[tuple[str, dict]] = []

    async def fake_do_post(self, endpoint, data, **kwargs):
        captured.append((endpoint, data))
        return {}

    monkeypatch.setattr(Bot, "_do_post", fake_do_post)
    bot = BaleBot(token="123:BALE_TOKEN")
    await bot._do_post(
        "sendMessage", {"chat_id": 1, "text": "<b>سلام</b>", "parse_mode": ParseMode.HTML}
    )

    endpoint, data = captured[0]
    assert endpoint == "sendMessage"
    assert data["text"] == " *سلام* "
    assert "parse_mode" not in data


@pytest.mark.asyncio
async def test_bale_bot_converts_captions(monkeypatch):
    captured: list[dict] = []

    async def fake_do_post(self, endpoint, data, **kwargs):
        captured.append(data)
        return {}

    monkeypatch.setattr(Bot, "_do_post", fake_do_post)
    bot = BaleBot(token="123:BALE_TOKEN")
    await bot._do_post(
        "sendPhoto",
        {"chat_id": 1, "photo": "file-id", "caption": "<i>caption</i>", "parse_mode": "HTML"},
    )

    assert captured[0]["caption"] == " _caption_ "
    assert "parse_mode" not in captured[0]


@pytest.mark.asyncio
async def test_bale_bot_leaves_plain_payload_untouched(monkeypatch):
    captured: list[dict] = []

    async def fake_do_post(self, endpoint, data, **kwargs):
        captured.append(data)
        return {}

    monkeypatch.setattr(Bot, "_do_post", fake_do_post)
    bot = BaleBot(token="123:BALE_TOKEN")
    await bot._do_post("sendMessage", {"chat_id": 1, "text": "a < b"})

    assert captured[0]["text"] == "a < b"


# --------------------------------------------------------------------------
# Bale channel references
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://web.bale.ai/chat?uid=4988441745", 4988441745),
        ("web.bale.ai/chat?uid=4988441745", 4988441745),
        ("https://ble.ir/post/6538474643817687952/123/1403", 6538474643817687952),
        ("https://ble.ir/my_channel", "@my_channel"),
        ("ble.ir/my_channel", "@my_channel"),
        ("@mhrezaa2", "@mhrezaa2"),
    ],
)
def test_normalize_bale_link_formats(raw, expected):
    assert normalize_channel_ref(raw) == expected


def test_normalize_keeps_invite_links():
    link = "https://ble.ir/join/SomeToken"
    assert normalize_channel_ref(link) == link


@pytest.mark.asyncio
async def test_resolve_bale_web_uid_tries_negative_id(monkeypatch):
    monkeypatch.setattr(
        channel_service, "settings", replace(config.settings, platform="bale")
    )
    channel = SimpleNamespace(id=-4988441745, title="کانال", username=None, type="channel")

    async def get_chat(ref):
        if str(ref).startswith("-"):
            return channel
        raise BadRequest("Bad Request: chat not found")

    mock_bot = SimpleNamespace(
        get_chat=AsyncMock(side_effect=get_chat),
        get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
    )
    client = BotClient(mock_bot)

    info = await resolve_channel(client, "https://web.bale.ai/chat?uid=4988441745")

    assert info.telegram_id == -4988441745
    tried = [call.args[0] for call in mock_bot.get_chat.await_args_list]
    assert "-4988441745" in tried or -4988441745 in tried


@pytest.mark.asyncio
async def test_resolve_bale_numeric_id_is_sent_as_string_first(monkeypatch):
    monkeypatch.setattr(
        channel_service, "settings", replace(config.settings, platform="bale")
    )
    channel = SimpleNamespace(id=-100, title="کانال", username=None, type="channel")
    mock_bot = SimpleNamespace(
        get_chat=AsyncMock(return_value=channel),
        get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
    )
    client = BotClient(mock_bot)

    await resolve_channel(client, "-100")

    assert mock_bot.get_chat.await_args_list[0].args[0] == "-100"


@pytest.mark.asyncio
async def test_resolve_rejects_invite_link(monkeypatch):
    monkeypatch.setattr(
        channel_service, "settings", replace(config.settings, platform="bale")
    )
    client = BotClient(SimpleNamespace(get_chat=AsyncMock()))

    with pytest.raises(ChannelAccessError, match="دعوت"):
        await resolve_channel(client, "https://ble.ir/join/SomeToken")


@pytest.mark.asyncio
async def test_resolve_telegram_does_not_retry_extra_candidates(monkeypatch):
    monkeypatch.setattr(
        channel_service, "settings", replace(config.settings, platform="telegram")
    )
    mock_bot = SimpleNamespace(get_chat=AsyncMock(side_effect=BadRequest("Bad Request: not found")))
    client = BotClient(mock_bot)

    with pytest.raises(ChannelAccessError):
        await resolve_channel(client, "-1001234567890")

    assert mock_bot.get_chat.await_count == 1
