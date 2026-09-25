from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telethon.crypto import AuthKey
from telethon.sessions import StringSession

from app.config import ConfigError
from app.telegram import client as client_module
from app.telegram.session import create_session


def fake_session_string() -> str:
    session = StringSession()
    session.set_dc(2, "149.154.167.51", 443)
    session.auth_key = AuthKey(bytes(range(256)))
    return session.save()


def test_string_session_bootstraps_persistent_file(tmp_path):
    path = str(tmp_path / "nested" / "forwarder")
    seed = fake_session_string()
    session = create_session(path, seed)
    try:
        assert session.dc_id == 2
        assert StringSession.save(session) == seed
    finally:
        session.close()

    # Subsequent starts use the persisted key, even without the bootstrap variable.
    restored = create_session(path)
    try:
        assert StringSession.save(restored) == seed
    finally:
        restored.close()


def test_existing_login_is_not_overwritten(tmp_path):
    path = str(tmp_path / "forwarder")
    seed = fake_session_string()
    create_session(path, seed).close()
    session = create_session(path, "a-new-or-invalid-value")
    try:
        assert StringSession.save(session) == seed
    finally:
        session.close()


def test_invalid_session_secret_is_not_exposed(tmp_path):
    secret = "not-a-valid-session-secret"
    with pytest.raises(ConfigError) as error:
        create_session(str(tmp_path / "forwarder"), secret)
    assert secret not in str(error.value)
    assert "TELETHON_STRING_SESSION" in str(error.value)
    # A failed bootstrap closes the database and permits a subsequent retry.
    create_session(str(tmp_path / "forwarder"), fake_session_string()).close()


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized, interactive", [(True, False), (False, False), (False, True)])
async def test_startup_login_modes(monkeypatch, authorized, interactive):
    client = SimpleNamespace(
        is_connected=Mock(return_value=False),
        connect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=authorized),
        disconnect=AsyncMock(),
        start=AsyncMock(),
        get_dialogs=AsyncMock(),
    )
    monkeypatch.setattr(client_module, "get_client", lambda: client)
    monkeypatch.setattr(client_module.sys, "stdin", SimpleNamespace(isatty=lambda: interactive))
    monkeypatch.setattr(client_module, "settings", SimpleNamespace(telethon_string_session=""))
    if not authorized and not interactive:
        with pytest.raises(ConfigError, match="interactive login is unavailable"):
            await client_module.ensure_started()
        client.disconnect.assert_awaited_once()
        client.start.assert_not_awaited()
    else:
        assert await client_module.ensure_started() is client
        assert client.start.await_count == int(not authorized)
    client.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_bootstrapped_login_populates_channel_cache(monkeypatch):
    client = SimpleNamespace(
        is_connected=lambda: True,
        is_user_authorized=AsyncMock(return_value=True),
        get_dialogs=AsyncMock(),
    )
    monkeypatch.setattr(client_module, "get_client", lambda: client)
    monkeypatch.setattr(client_module, "settings", SimpleNamespace(telethon_string_session="seed"))
    assert await client_module.ensure_started() is client
    client.get_dialogs.assert_awaited_once()
