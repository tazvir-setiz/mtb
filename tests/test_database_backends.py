from app.database.database import create_app_engine, normalize_database_url


def test_normalize_database_url():
    assert normalize_database_url("sqlite:///data/test.db") == "sqlite:///data/test.db"
    assert (
        normalize_database_url("postgres://user:pass@localhost:5432/mydb")
        == "postgresql+psycopg://user:pass@localhost:5432/mydb"
    )
    assert (
        normalize_database_url("postgresql://user:pass@localhost:5432/mydb")
        == "postgresql+psycopg://user:pass@localhost:5432/mydb"
    )
    assert (
        normalize_database_url("postgresql+psycopg://user:pass@localhost:5432/mydb")
        == "postgresql+psycopg://user:pass@localhost:5432/mydb"
    )


def test_create_app_engine_sqlite():
    engine = create_app_engine("sqlite:///:memory:")
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == ":memory:"


def test_create_app_engine_postgres():
    # Verify PostgreSQL engine builds with pool parameters and psycopg driver
    url = "postgresql+psycopg://test_user:test_pass@localhost:5432/test_db"
    engine = create_app_engine(url)
    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
    assert engine.pool._pre_ping is True
    assert engine.pool._recycle == 300
