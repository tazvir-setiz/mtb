import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from telethon.errors import ChatAdminRequiredError

from app.database import database
from app.database.database import get_session
from app.database.models import (
    Channel,
    ChannelType,
    ForwardJob,
    JobStatus,
    MessageStatus,
    ReviewRequest,
    Settings,
)
from app.database.repository import (
    ChannelRepository,
    ForwardedMessageRepository,
    ForwardJobRepository,
    SettingsRepository,
)
from app.handlers import dashboard, source, transfer
from app.handlers.states import KEY_PENDING_CHANNEL
from app.services import review_drafts, review_service, review_store, transfer_service
from app.services.ai_policy import AIReviewRequired
from app.services.fanout import delivery_key
from app.services.transfer_routes import job_routes
from app.telegram import auto_forward, forward_service, message_sender
from app.ui.buttons.channels import channel_management


def original(mid=7):
    return SimpleNamespace(id=mid, message=str(mid), media=None, entities=[], poll=None)


def client_for(message=None):
    return SimpleNamespace(
        get_messages=AsyncMock(return_value=[message or original()]),
        send_message=AsyncMock(return_value=SimpleNamespace(id=99)),
        add_event_handler=Mock(),
        remove_event_handler=Mock(),
    )


def routes_for(source_id=-1001, destinations=(-2001, -2002, -2003)):
    with get_session() as session:
        return [
            (destination, ForwardJobRepository.create(session, source_id, destination, 7, 7, 1).id)
            for destination in destinations
        ]


@pytest.mark.parametrize("source_count,destination_count", [(1, 1), (1, 3), (3, 1), (3, 3)])
async def test_auto_route_matrix_guard_once_per_source(
    monkeypatch, source_count, destination_count
):
    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    sources = [-1001 - i for i in range(source_count)]
    destinations = [-2001 - i for i in range(destination_count)]
    with get_session() as session:
        for value in sources:
            ChannelRepository.upsert(session, value, str(value), ChannelType.SOURCE)
        for value in destinations:
            ChannelRepository.upsert(session, value, str(value), ChannelType.DESTINATION)
    guard = AsyncMock(return_value="prepared")
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", guard)
    client = client_for()
    assert await auto_forward.enable(client)
    for value in sources:
        await auto_forward._handler(
            SimpleNamespace(chat_id=value, client=client, message=original())
        )
    assert guard.await_count == source_count
    assert client.send_message.await_count == source_count * destination_count
    with get_session() as session:
        for src in sources:
            for dst in destinations:
                assert ForwardedMessageRepository.exists(session, src, 7, dst)
    await auto_forward.disable(client)


@pytest.mark.parametrize("flow", ["auto", "manual"])
@pytest.mark.parametrize("review", [False, True])
async def test_guard_once_three_destinations_and_shared_review(monkeypatch, flow, review):
    guard = AsyncMock(
        side_effect=AIReviewRequired("review") if review else None, return_value="safe"
    )
    monkeypatch.setattr(message_sender, "apply_ai_guardrails", guard)
    client = client_for()
    if flow == "auto":
        routes = routes_for()
        await auto_forward._on_new_message(
            SimpleNamespace(client=client, message=original()), -1001, routes
        )
    else:
        job = transfer_service.create_job_for_ids(-1001, [-2001, -2002, -2003], [7])
        with get_session() as session:
            routes = job_routes(session, ForwardJobRepository.get(session, job))
        await forward_service.forward_range(client, job, -1001, -2001, [7])
    assert guard.await_count == 1
    assert client.send_message.await_count == (0 if review else 3)
    if review:
        with get_session() as session:
            rows = session.scalars(select(ReviewRequest)).all()
        assert len(rows) == 1
        assert review_store.routes(rows[0]) == routes
        await review_service.decide(
            rows[0].id, review_drafts.version(rows[0]), "approve", 111, client
        )
        assert client.send_message.await_count == 3
        assert guard.await_count == 1


@pytest.mark.parametrize("flow", ["manual", "review"])
async def test_partial_failure_retries_only_failed_destination(flow):
    client = client_for()
    client.send_message.side_effect = [
        SimpleNamespace(id=1),
        ChatAdminRequiredError(None),
        SimpleNamespace(id=3),
    ]
    if flow == "manual":
        job = transfer_service.create_job_for_ids(-1001, [-2001, -2002, -2003], [7])
        await forward_service.forward_range(client, job, -1001, -2001, [7])
        with get_session() as session:
            routes = job_routes(session, ForwardJobRepository.get(session, job))
    else:
        routes = routes_for()
        row = review_store.enqueue_routes(original(), -1001, routes, "review")
        await review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
        assert review_store.get(row.id).status == "pending"
    with get_session() as session:
        records = {
            r.destination_channel_id: r.status for r in ForwardedMessageRepository.recent(session)
        }
        assert records == {
            -2001: MessageStatus.SUCCESS,
            -2002: MessageStatus.FAILED,
            -2003: MessageStatus.SUCCESS,
        }
    client.send_message.reset_mock()
    client.send_message.side_effect = None
    if flow == "manual":
        await forward_service.retry_failed(client, job)
    else:
        await review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
    client.send_message.assert_awaited_once()
    assert client.send_message.call_args.kwargs["entity"] == -2002
    with get_session() as session:
        for _, jid in routes:
            job_row = ForwardJobRepository.get(session, jid)
            assert job_row.successful_messages == 1
            assert job_row.failed_messages == 0


async def test_reject_marks_all_routes_without_overwriting_success():
    routes = routes_for()
    row = review_store.enqueue_routes(original(), -1001, routes, "review")
    from app.services.forward_results import record_result

    record_result(routes[0][1], -1001, 7, -2001, MessageStatus.SUCCESS, destination_message_id=10)
    await review_service.decide(row.id, review_drafts.version(row), "reject", 111, None)
    with get_session() as session:
        records = {r.destination_channel_id: r for r in ForwardedMessageRepository.recent(session)}
        assert records[-2001].status == MessageStatus.SUCCESS
        assert records[-2001].destination_message_id == 10
        assert records[-2002].status == records[-2003].status == MessageStatus.SKIPPED
        assert ForwardJobRepository.get(session, routes[0][1]).successful_messages == 1


@pytest.mark.parametrize("kind", ["source", "destination"])
async def test_channel_add_remove_preserves_others_and_refreshes(monkeypatch, kind):
    typ = ChannelType(kind)
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "first", typ)
        ChannelRepository.upsert(
            session,
            -1002,
            "other role",
            ChannelType.DESTINATION if kind == "source" else ChannelType.SOURCE,
        )
    refresh = AsyncMock(return_value=True)
    monkeypatch.setattr(source.auto_forward, "is_enabled", lambda: True)
    monkeypatch.setattr(source.auto_forward, "refresh_listener", refresh)
    monkeypatch.setattr(source, "ensure_started", AsyncMock(return_value=object()))
    monkeypatch.setattr(dashboard, "show_dashboard", AsyncMock())
    context = SimpleNamespace(
        user_data={
            KEY_PENDING_CHANNEL: dict(
                kind=kind, telegram_id=-1002, title="second", username=None, message_id=7
            )
        }
    )
    update = SimpleNamespace(
        callback_query=SimpleNamespace(
            message=SimpleNamespace(message_id=7, reply_text=AsyncMock()),
            edit_message_text=AsyncMock(),
            data=f"{kind}:remove:-1002",
        )
    )
    await source.handle_confirm(update, context, kind)
    with get_session() as session:
        assert [c.telegram_id for c in ChannelRepository.get_all_by_type(session, typ)] == [
            -1001,
            -1002,
        ]
    await source.remove_channel(update, context, kind)
    with get_session() as session:
        assert [c.telegram_id for c in ChannelRepository.get_all_by_type(session, typ)] == [-1001]
        assert session.scalar(select(Channel).where(Channel.telegram_id == -1002)) is not None
    assert refresh.await_count == 2


def test_remove_callback_fits_telegram_limit():
    for kind in ("source", "destination"):
        buttons = channel_management(
            kind, [SimpleNamespace(title="x" * 200, telegram_id=-1001234567890123)], removing=True
        )
        assert all(
            len(b.callback_data.encode()) <= 64 for row in buttons.inline_keyboard for b in row
        )


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "not json",
        "{}",
        "null",
        "[]",
        "[{}]",
        '[{"destination_id":true}]',
        '[{"destination_id":1,"job_id":"bad"}]',
    ],
)
def test_legacy_review_fallback_for_malformed_routes(raw):
    row = review_store.enqueue(original(), -1001, -2001, None, "review")
    with get_session() as session:
        session.query(Settings).filter_by(key=f"review_routes:{row.id}").delete()
        if raw is not None:
            SettingsRepository.set(session, f"review_routes:{row.id}", raw)
    assert review_store.routes(row) == [(-2001, None)]


def test_shared_review_merges_routes_regardless_of_primary_order():
    row = review_store.enqueue_routes(original(), -1001, [(-2001, None), (-2002, None)], "review")
    updated = review_store.enqueue_routes(
        original(), -1001, [(-2003, None), (-2001, None)], "review"
    )
    assert updated.id == row.id
    assert review_store.routes(updated) == [(-2001, None), (-2002, None), (-2003, None)]
    assert review_store.find(-1001, 7, -2003).id == row.id
    assert len(review_store.pending()) == 1


def test_full_clear_removes_reviews_and_route_metadata():
    job = transfer_service.create_job_for_ids(-1001, [-2001, -2002], [7])
    review_store.enqueue(original(), -1001, -2001, job, "review")
    with get_session() as session:
        SettingsRepository.set(session, "route_sending:-1001:7:-2001", "1")
        SettingsRepository.set(session, "signature_text", "keep")
        SettingsRepository.clear_all_data(session)
    with get_session() as session:
        assert session.scalars(select(ReviewRequest)).all() == []
        assert session.scalars(select(ForwardJob)).all() == []
        assert [row.key for row in session.scalars(select(Settings))] == ["signature_text"]


def test_legacy_sqlite_channel_migration_is_idempotent(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE channels (id INTEGER PRIMARY KEY, telegram_id BIGINT, username VARCHAR(255), title VARCHAR(255), type VARCHAR(11), created_at DATETIME, updated_at DATETIME)"
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX ix_channels_telegram_id ON channels (telegram_id)"))
        conn.execute(
            text(
                "INSERT INTO channels VALUES (42,-1001,NULL,'Legacy','SOURCE','2020-01-01','2020-01-01')"
            )
        )
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    database.init_db()
    with Session(engine) as session:
        assert session.get(Channel, 42).title == "Legacy"
        ChannelRepository.upsert(session, -1001, "Destination too", ChannelType.DESTINATION)
        session.commit()
        assert len(session.scalars(select(Channel)).all()) == 2
    engine.dispose()


async def test_manual_requires_source_and_allows_destination_subset():
    with get_session() as session:
        for value in (-1001, -1002):
            ChannelRepository.upsert(session, value, str(value), ChannelType.SOURCE)
        for value in (-2001, -2002, -2003):
            ChannelRepository.upsert(session, value, str(value), ChannelType.DESTINATION)
    assert transfer_service.get_channels()[0] is None
    query = SimpleNamespace(edit_message_text=AsyncMock(), answer=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})
    await transfer.show_transfer_menu(update, context)
    assert "transfer_source" not in context.user_data
    query.data = "transfer:source:-1002"
    await transfer.select_source(update, context)
    for dst in (-2001, -2003):
        query.data = f"transfer:destination:{dst}"
        await transfer.toggle_destination(update, context)
    await transfer.confirm_routes(update, context)
    selected = transfer_service.get_channels(context.user_data)
    assert selected[:2] == (-1002, [-2001, -2003])
    with get_session() as session:
        ChannelRepository.remove(session, ChannelType.DESTINATION, -2003)
    assert transfer_service.get_channels(context.user_data)[1] == []


async def test_group_resume_preserves_sparse_selection_and_all_destinations():
    job_id = transfer_service.create_job_for_ids(-1001, [-2001, -2002], [7, 20])
    client = client_for()
    client.get_messages.side_effect = lambda source, ids: [original(ids[0])]

    async def progress(snapshot):
        if not snapshot.stopped:
            forward_service.request_stop(job_id)

    await forward_service.forward_range(client, job_id, -1001, -2001, [7, 20], progress)
    with get_session() as session:
        job = ForwardJobRepository.get(session, job_id)
        remaining = transfer_service.remaining_ids(session, job)
        assert remaining == [20]
        assert all(
            ForwardJobRepository.get(session, j).status == JobStatus.PAUSED
            for _, j in job_routes(session, job)
        )
    await forward_service.forward_range(client, job_id, -1001, -2001, remaining)
    assert client.send_message.await_count == 4
    assert [
        call.args[1] if len(call.args) > 1 else call.kwargs["ids"]
        for call in client.get_messages.await_args_list
    ] == [[7], [20]]


@pytest.mark.parametrize("competitor", ["auto", "manual"])
@pytest.mark.parametrize("review_first", [False, True])
async def test_review_races_send_once(monkeypatch, competitor, review_first):
    routes = routes_for(destinations=(-2001,))
    client = client_for()
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(**kwargs):
        entered.set()
        await release.wait()
        return SimpleNamespace(id=99)

    client.send_message.side_effect = send

    async def other():
        if competitor == "auto":
            await auto_forward._on_new_message(
                SimpleNamespace(client=client, message=original()), -1001, routes
            )
        else:
            await forward_service.forward_range(client, routes[0][1], -1001, -2001, [7])

    if review_first:
        row = review_store.enqueue_routes(original(), -1001, routes, "review")
        task = asyncio.create_task(
            review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
        )
        await asyncio.wait_for(entered.wait(), 3)
        other_task = asyncio.create_task(other())
    else:
        task = asyncio.create_task(other())
        await asyncio.wait_for(entered.wait(), 3)
        # Simulate an already queued old review arriving while delivery is in flight.
        row = review_store.enqueue_routes(original(), -1001, routes, "review")
        other_task = asyncio.create_task(
            review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
        )
    await asyncio.sleep(0)
    release.set()
    await asyncio.wait_for(asyncio.gather(task, other_task), 3)
    client.send_message.assert_awaited_once()


async def test_uncertain_manual_send_blocks_retry_auto_and_review_until_reset():
    job = transfer_service.create_job_for_ids(-1001, [-2001, -2002], [7])
    client = client_for()
    client.send_message.side_effect = [TimeoutError(), SimpleNamespace(id=2)]
    await forward_service.forward_range(client, job, -1001, -2001, [7])
    row = review_store.find_for_message(-1001, 7)
    assert row.status == "uncertain"
    assert client.send_message.await_count == 2
    await forward_service.retry_failed(client, job)
    await auto_forward._on_new_message(
        SimpleNamespace(client=client, message=original()), -1001, routes_for()
    )
    await review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
    assert client.send_message.await_count == 2
    await review_service.decide(row.id, review_drafts.version(row), "reset", 111, client)
    client.send_message.side_effect = None
    row = review_store.get(row.id)
    await review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
    assert [call.kwargs["entity"] for call in client.send_message.await_args_list] == [
        -2001,
        -2002,
        -2001,
        -2003,
    ]


async def test_interrupted_delivery_marker_prevents_automatic_resend():
    routes = routes_for(destinations=(-2001,))
    with get_session() as session:
        SettingsRepository.set(session, delivery_key(-1001, 7, -2001), "1")
    client = client_for()
    await auto_forward._on_new_message(
        SimpleNamespace(client=client, message=original()), -1001, routes
    )
    client.send_message.assert_not_awaited()
    assert review_store.find_for_message(-1001, 7).status == "uncertain"


async def test_retry_survives_route_record_reassignment_and_preserves_skips():
    from app.services.forward_results import record_result

    job = transfer_service.create_job_for_ids(-1001, [-2001, -2002, -2003], [7])
    with get_session() as session:
        routes = job_routes(session, ForwardJobRepository.get(session, job))
    record_result(routes[0][1], -1001, 7, -2001, MessageStatus.FAILED)
    record_result(routes[1][1], -1001, 7, -2002, MessageStatus.SKIPPED)
    # Another operation now owns the failure record; the original job must remain retryable.
    competing_job = routes_for(destinations=(-2001,))[0][1]
    record_result(competing_job, -1001, 7, -2001, MessageStatus.FAILED)
    assert transfer_service.get_failed_items(job)[0][0] == 7
    client = client_for()
    await forward_service.retry_failed(client, job)
    # D1 failed, D2 was deliberately skipped, D3 had not yet been processed.
    assert [call.kwargs["entity"] for call in client.send_message.await_args_list] == [-2001, -2003]
    client.send_message.reset_mock()
    await forward_service.retry_failed(client, competing_job)
    client.send_message.assert_not_awaited()
    with get_session() as session:
        assert ForwardJobRepository.get(session, job).failed_messages == 0
        assert ForwardJobRepository.get(session, competing_job).failed_messages == 0
        assert ForwardJobRepository.get(session, routes[1][1]).skipped_messages == 1


async def test_large_channel_lists_are_paginated_and_selection_survives_pages():
    from app.ui.buttons.transfer import destination_selection

    with get_session() as session:
        for value in range(25):
            ChannelRepository.upsert(session, -1000 - value, "<large>" * 30, ChannelType.SOURCE)
            ChannelRepository.upsert(
                session, -2000 - value, "<large>" * 30, ChannelType.DESTINATION
            )
    query = SimpleNamespace(data="menu:source:1", edit_message_text=AsyncMock(), answer=AsyncMock())
    context = SimpleNamespace(user_data={})
    update = SimpleNamespace(callback_query=query)
    await source.show_channels(update, context, "source")
    text = query.edit_message_text.call_args.args[0]
    assert "11." in text and "20." in text and "21." not in text
    assert len(text) < 4096
    assert "&lt;large&gt;" in text
    await transfer.show_transfer_menu(update, context)
    query.data = "transfer:source:-1000"
    await transfer.select_source(update, context)
    query.data = "transfer:destination:-2000"
    await transfer.toggle_destination(update, context)
    query.data = "transfer:destinations:2"
    await transfer.show_destinations(update, context)
    query.data = "transfer:destination:-2024"
    await transfer.toggle_destination(update, context)
    assert transfer_service.get_channels(context.user_data)[:2] == (-1000, [-2000, -2024])
    _, channels = transfer_service.configured_channels()
    markup = destination_selection(channels, [-2000, -2024], 2)
    assert len(markup.inline_keyboard) <= 13
    assert all(
        len(button.callback_data.encode()) <= 64 for row in markup.inline_keyboard for button in row
    )


async def test_legacy_review_without_route_metadata_resolves_after_restart():
    row = review_store.enqueue(original(), -1001, -2001, None, "review")
    with get_session() as session:
        session.query(Settings).filter_by(key=f"review_routes:{row.id}").delete()
    database.init_db()
    client = client_for()
    await review_service.decide(row.id, review_drafts.version(row), "approve", 111, client)
    client.send_message.assert_awaited_once()
    with get_session() as session:
        assert ForwardedMessageRepository.exists(session, -1001, 7, -2001)
    await forward_service.forward_range(
        client, routes_for(destinations=(-2001,))[0][1], -1001, -2001, [7]
    )
    client.send_message.assert_awaited_once()


async def test_listener_refresh_replaces_routes_and_ignores_stale_events(monkeypatch):
    monkeypatch.setattr(auto_forward, "_handler", None)
    monkeypatch.setattr(auto_forward, "_registered_client", None)
    client = client_for()
    with get_session() as session:
        ChannelRepository.upsert(session, -1001, "source", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -2001, "destination", ChannelType.DESTINATION)
    await auto_forward.enable(client)
    old_handler = auto_forward._handler
    with get_session() as session:
        ChannelRepository.upsert(session, -1002, "second source", ChannelType.SOURCE)
        ChannelRepository.upsert(session, -2002, "second destination", ChannelType.DESTINATION)
        ChannelRepository.remove(session, ChannelType.DESTINATION, -2001)
    assert await auto_forward.refresh_listener(client)
    client.remove_event_handler.assert_called_once_with(old_handler)
    await old_handler(SimpleNamespace(chat_id=-1001, client=client, message=original()))
    client.send_message.assert_not_awaited()
    await auto_forward._handler(SimpleNamespace(chat_id=-1002, client=client, message=original()))
    client.send_message.assert_awaited_once()
    assert client.send_message.call_args.kwargs["entity"] == -2002
    await auto_forward.disable(client)
