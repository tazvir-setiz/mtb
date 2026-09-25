from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import export_session


@pytest.mark.asyncio
async def test_export_writes_secret_without_printing_it(monkeypatch, tmp_path, capsys):
    secret = "dummy-session-secret"
    client = SimpleNamespace(session=object(), is_bot=AsyncMock(return_value=False))
    monkeypatch.setattr(export_session, "ensure_started", AsyncMock(return_value=client))
    stopped = AsyncMock()
    monkeypatch.setattr(export_session, "stop_client", stopped)
    monkeypatch.setattr(export_session.StringSession, "save", lambda _: secret)
    path = tmp_path / "sessions" / "railway-session.txt"
    await export_session.export_session(path)
    assert path.read_text() == secret
    assert secret not in capsys.readouterr().out
    stopped.assert_awaited_once()
    with pytest.raises(FileExistsError):
        await export_session.export_session(path)
    assert path.read_text() == secret


@pytest.mark.asyncio
async def test_export_disconnects_when_login_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        export_session, "ensure_started", AsyncMock(side_effect=RuntimeError("login"))
    )
    stopped = AsyncMock()
    monkeypatch.setattr(export_session, "stop_client", stopped)
    with pytest.raises(RuntimeError, match="login"):
        await export_session.export_session(tmp_path / "session.txt")
    stopped.assert_awaited_once()
