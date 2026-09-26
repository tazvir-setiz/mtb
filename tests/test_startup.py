import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from telegram.error import InvalidToken, NetworkError

import main


@pytest.mark.parametrize(
    "error,exit_code", [(None, 0), (NetworkError("offline"), 1), (InvalidToken("invalid"), 1)]
)
def test_startup_owns_loop_and_has_bounded_retries(monkeypatch, error, exit_code):
    loops = []

    def polling(**kwargs):
        assert kwargs["bootstrap_retries"] == 3
        assert kwargs["close_loop"] is False
        loop = asyncio.get_event_loop()
        loops.append(loop)
        assert loop.run_until_complete(asyncio.sleep(0, result="ready")) == "ready"
        if error:
            raise error

    application = SimpleNamespace(run_polling=polling)
    monkeypatch.setattr(main, "setup_logging", Mock())
    monkeypatch.setattr(main, "init_db", Mock())
    monkeypatch.setattr(main, "recover_interrupted", Mock())
    monkeypatch.setattr(main, "build_application", lambda: application)
    assert main.main() == exit_code
    assert loops[0].is_closed()
    assert application.post_init is main._post_init
    assert application.post_shutdown is main._post_shutdown
