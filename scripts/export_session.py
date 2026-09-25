"""Export a local login for Railway without printing credentials to the terminal."""

import asyncio
import os
from pathlib import Path

from telethon.sessions import StringSession

from app.config import BASE_DIR
from app.telegram.client import ensure_started, stop_client

OUTPUT_PATH = BASE_DIR / "sessions" / "railway-session.txt"


async def export_session(output_path: Path = OUTPUT_PATH) -> None:
    try:
        client = await ensure_started()
        if await client.is_bot():
            raise RuntimeError("A Telegram user account session is required, not a bot session.")
        session_string = StringSession.save(client.session)
        if not session_string:
            raise RuntimeError("The session has no authorization key. Log in before exporting.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Refuse to overwrite an existing secret. On POSIX, restrict access to its owner.
        fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(session_string)
        print(f"Session saved to {output_path}. Copy its contents to TELETHON_STRING_SESSION.")
        print(
            "Keep this file private. Do not commit or share it. Stop the local bot before deploying."
        )
    finally:
        await stop_client()


if __name__ == "__main__":
    if OUTPUT_PATH.exists():
        raise SystemExit(
            f"{OUTPUT_PATH} already exists. Move or remove it before exporting a new session."
        )
    asyncio.run(export_session())
