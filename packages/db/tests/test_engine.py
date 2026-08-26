import os

import pytest
from merchantos_db import create_db_engine, normalize_database_url, ping_database


def test_rejects_non_postgres_url() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        create_db_engine("sqlite:///:memory:")


def test_uses_psycopg3_driver() -> None:
    engine = create_db_engine("postgresql://merchantos:merchantos@localhost:5432/merchantos")
    assert engine.url.drivername == "postgresql+psycopg"
    assert (
        normalize_database_url("postgresql://localhost/db") == "postgresql+psycopg://localhost/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg://localhost/db")
        == "postgresql+psycopg://localhost/db"
    )


@pytest.mark.integration
def test_postgres_connectivity() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for integration tests")
    ping_database(create_db_engine(url))
