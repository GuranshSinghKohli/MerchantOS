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


def test_production_urls_require_rds_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    assert (
        normalize_database_url("postgresql://merchantos_app:x@10.0.0.5:5432/merchantos")
        == "postgresql+psycopg://merchantos_app:x@10.0.0.5:5432/merchantos?sslmode=require"
    )
    assert (
        normalize_database_url(
            "postgresql://merchantos_app:x@10.0.0.5:5432/merchantos?sslmode=disable"
        )
        == "postgresql+psycopg://merchantos_app:x@10.0.0.5:5432/merchantos?sslmode=disable"
    )


@pytest.mark.integration
def test_postgres_connectivity() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is required for integration tests")
    ping_database(create_db_engine(url))
