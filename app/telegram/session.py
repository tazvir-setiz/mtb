from pathlib import Path

from telethon.sessions import SQLiteSession, StringSession

from app.config import ConfigError


def create_session(path: str, session_string: str = "") -> SQLiteSession:
    """Keep entity caches on disk; import credentials only into an empty session."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    session = SQLiteSession(path)
    try:
        if not session.auth_key and session_string:
            try:
                seed = StringSession(session_string)
            except Exception:
                raise ConfigError(
                    "Invalid TELETHON_STRING_SESSION. Regenerate it locally with "
                    "python -m scripts.export_session."
                ) from None
            if not seed.auth_key:
                raise ConfigError("TELETHON_STRING_SESSION contains no authorization key.")
            session.set_dc(seed.dc_id, seed.server_address, seed.port)
            session.auth_key = seed.auth_key
            session.save()
        return session
    except Exception:
        session.close()
        raise
