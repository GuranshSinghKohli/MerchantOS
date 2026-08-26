import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from merchantos_api.deps import db_engine, settings
from merchantos_db.engine import create_db_engine, session_scope
from merchantos_db.models import Base
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(scope="session", autouse=True)
def _oauth_env() -> None:
    os.environ.setdefault("SHOPIFY_API_KEY", "test_key")
    os.environ.setdefault("SHOPIFY_API_SECRET", "test_secret")
    os.environ.setdefault("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    os.environ.setdefault("TOKEN_ENCRYPTION_KEY_VERSION", "test")
    settings.cache_clear()
    db_engine.cache_clear()


@pytest.fixture
def postgres() -> Generator[None, None, None]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for OAuth persistence tests")
    alembic_cfg = Config(str(ROOT / "packages/db/alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(ROOT / "packages/db/alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")
    engine = create_db_engine(url)
    with session_scope(engine) as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    settings.cache_clear()
    db_engine.cache_clear()
    yield
    db_engine.cache_clear()
