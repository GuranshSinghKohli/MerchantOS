import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from merchantos_db.engine import create_db_engine, session_scope
from merchantos_db.models import Base
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def postgres() -> Generator[None, None, None]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for MCP isolation tests")
    alembic_cfg = Config(str(ROOT / "packages/db/alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(ROOT / "packages/db/alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(alembic_cfg, "head")
    engine = create_db_engine(url)
    with session_scope(engine) as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    yield
