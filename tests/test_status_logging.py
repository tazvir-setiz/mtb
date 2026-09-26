import asyncio
import logging
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app import logging_config
from app.log_context import context, traced
from app.status_logging import log_status, monitor_status
from app.telegram import auto_forward


def test_logging_setup_is_idempotent_and_captures_warnings(monkeypatch, tmp_path):
    root = logging.getLogger()
    old_level = root.level
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        logging_config, "settings", replace(logging_config.settings, log_to_file=True)
    )
    try:
        logging_config.setup_logging()
        logging_config.setup_logging()
        assert sum(bool(getattr(h, "forwarder_handler", False)) for h in root.handlers) == 3
        logging.getLogger(__name__).warning("test_warning")
        assert "test_warning" in (tmp_path / "logs/error.log").read_text(encoding="utf-8")
        assert "UTC" in (tmp_path / "logs/app.log").read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            if getattr(handler, "forwarder_handler", False):
                root.removeHandler(handler)
                handler.close()
        root.setLevel(old_level)


@pytest.mark.asyncio
async def test_trace_isolated_between_tasks_and_reset_after_failure():
    @traced
    async def operation(source_id, msg_id):
        await asyncio.sleep(0)
        assert context.get() == {"source_id": source_id, "msg_id": msg_id}
        if msg_id == 2:
            raise ValueError("test")
        return dict(context.get())

    results = await asyncio.gather(operation(10, 1), operation(20, 2), return_exceptions=True)
    assert results[0] == {"source_id": 10, "msg_id": 1}
    assert isinstance(results[1], ValueError)
    assert context.get() == {}


@pytest.mark.asyncio
async def test_cancelled_queue_waiter_does_not_leak_count_or_release_lock(monkeypatch):
    monkeypatch.setattr(auto_forward, "_processing_lock", asyncio.Lock())
    monkeypatch.setattr(auto_forward, "_waiting", 0)

    async def queued():
        async with auto_forward.processing_slot():
            pass

    async with auto_forward.processing_slot():
        task = asyncio.create_task(queued())
        await asyncio.sleep(0)
        assert auto_forward.status_snapshot()["waiting"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert auto_forward.status_snapshot()["waiting"] == 0
        assert auto_forward.status_snapshot()["processing"]
    assert not auto_forward.status_snapshot()["processing"]


def test_status_does_not_include_credentials(monkeypatch, caplog):
    monkeypatch.setattr(
        "app.status_logging.load_ai_settings",
        lambda: SimpleNamespace(
            enabled=True, model="test-model", api_key="private-api-key", base_url="private-url"
        ),
    )
    with caplog.at_level(logging.INFO):
        log_status(SimpleNamespace(is_connected=lambda: False), time.monotonic())
    assert "telegram_connected=False" in caplog.text
    assert "api_key_configured=True" in caplog.text
    assert "private-api-key" not in caplog.text
    assert "private-url" not in caplog.text


@pytest.mark.asyncio
async def test_monitor_survives_reporting_error_and_cancels(monkeypatch, caplog):
    called = asyncio.Event()

    def fail(*args):
        called.set()
        raise ValueError("secret data")

    monkeypatch.setattr("app.status_logging.log_status", fail)
    task = asyncio.create_task(monitor_status(None))
    await called.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "Status report failed type=ValueError" in caplog.text
    assert "secret data" not in caplog.text
