from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database.models import Base


def normalize_database_url(url: str) -> str:
    """Normalize database connection URLs for PostgreSQL and cloud providers."""
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _ensure_sqlite_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_app_engine(database_url: str):
    url = normalize_database_url(database_url)
    _ensure_sqlite_dir(url)
    is_sqlite = url.startswith("sqlite")
    is_postgres = "postgres" in url

    if is_postgres:
        return create_engine(
            url,
            hide_parameters=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return create_engine(
        url,
        hide_parameters=True,
        connect_args=(
            {"check_same_thread": False, "timeout": 30}
            if is_sqlite
            else {}
        ),
    )


engine = create_app_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        finally:
            cursor.close()


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
