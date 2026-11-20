from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, NetworkError

from app.telegram import callback_ack
from app.telegram.callback_ack import ack, already_answered, is_stale_query_error

STALE = "Query is too old and response timeout expired or query id is invalid"


@pytest.fixture(autouse=True)
def _clean_tracking():
    callback_ack._answered.clear()
    yield
    callback_ack._answered.clear()


@pytest.mark.asyncio
async def test_ack_answers_a_query_only_once():
    query = SimpleNamespace(id="query-1", answer=AsyncMock())

    assert await ack(query) is True
    assert await ack(query) is False
    assert await ack(query, "دوباره") is False

    query.answer.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_ack_passes_text_and_alert():
    query = SimpleNamespace(id="query-2", answer=AsyncMock())

    assert await ack(query, "انجام شد", show_alert=True) is True

    query.answer.assert_awaited_once_with("انجام شد", show_alert=True)
    assert already_answered(query) is True


@pytest.mark.asyncio
async def test_ack_treats_an_expired_query_as_answered():
    query = SimpleNamespace(id="query-3", answer=AsyncMock(side_effect=BadRequest(STALE)))

    assert await ack(query, "دیر شد") is False
    assert already_answered(query) is True


@pytest.mark.asyncio
async def test_ack_never_raises_on_transport_errors():
    query = SimpleNamespace(id="query-4", answer=AsyncMock(side_effect=NetworkError("offline")))

    assert await ack(query) is False


@pytest.mark.asyncio
async def test_ack_ignores_missing_query():
    assert await ack(None) is False


@pytest.mark.asyncio
async def test_ack_without_query_id_is_not_deduplicated():
    # Objects the library builds in tests carry no id; they must still be acknowledged.
    query = SimpleNamespace(answer=AsyncMock())

    assert await ack(query) is True
    assert await ack(query) is True
    assert query.answer.await_count == 2


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (BadRequest(STALE), True),
        (BadRequest("Bad Request: query is too old"), True),
        (BadRequest("QUERY_ID_INVALID"), True),
        (BadRequest("Message is not modified"), False),
        (NetworkError("offline"), False),
    ],
)
def test_stale_query_detection(error, expected):
    assert is_stale_query_error(error) is expected
