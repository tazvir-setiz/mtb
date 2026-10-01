from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database.models import Base


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    hide_parameters=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        # Legacy SQLAlchemy schema used a unique index on telegram_id alone.
        # Replace only that index; preserve all channel rows and their IDs.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_role "
                    "ON channels (type, telegram_id)"
                )
            )
            indexes = connection.execute(text("PRAGMA index_list(channels)")).all()
            if any(row[1] == "ix_channels_telegram_id" and row[2] for row in indexes):
                connection.execute(text("DROP INDEX ix_channels_telegram_id"))
                connection.execute(
                    text("CREATE INDEX ix_channels_telegram_id ON channels (telegram_id)")
                )


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
