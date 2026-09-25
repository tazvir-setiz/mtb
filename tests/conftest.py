import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("ADMIN_IDS", "111,222")
os.environ.setdefault("FORWARD_DELAY", "0")
os.environ.setdefault("PROGRESS_UPDATE_INTERVAL", "0")
os.environ["AI_ENABLED"] = "false"
os.environ["PROXY_ENABLED"] = "false"

_tmp_dir = tempfile.TemporaryDirectory(prefix="forwarder-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir.name) / 'test.db'}"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.database.database import engine, init_db  # noqa: E402
from app.database.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database_lifetime():
    yield
    engine.dispose()
    _tmp_dir.cleanup()


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield
