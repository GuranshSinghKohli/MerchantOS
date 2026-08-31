"""Controlled migration entrypoint. Never runs from a request handler."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from merchantos_db.engine import normalize_database_url


def _pg_quote_literal(value: str) -> str:
    """Quote a PostgreSQL string literal. PASSWORD cannot use bind parameters."""
    if "\x00" in value:
        raise ValueError("password must not contain NUL")
    return "'" + value.replace("'", "''") + "'"


def _alembic_ini() -> Path:
    configured = os.environ.get("ALEMBIC_INI")
    candidates = [
        Path(configured) if configured else None,
        Path("/app/packages/db/alembic.ini"),
        Path(__file__).resolve().parents[2] / "alembic.ini",
        Path.cwd() / "packages/db/alembic.ini",
    ]
    for path in candidates:
        if path is not None and path.is_file():
            return path
    raise RuntimeError("alembic.ini not found; set ALEMBIC_INI")


def _alembic_config(database_url: str) -> Config:
    ini = _alembic_ini()
    cfg = Config(str(ini))
    # alembic.ini uses a cwd-relative script_location; pin it to the ini dir.
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", normalize_database_url(database_url))
    return cfg


def ensure_app_role(database_url: str, password: str) -> None:
    """Create merchantos_app before Alembic so 0004 does not use the compose password."""
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    with engine.begin() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'merchantos_app'")
        ).scalar()
        if exists is None:
            connection.execute(text("CREATE ROLE merchantos_app LOGIN NOSUPERUSER NOBYPASSRLS"))
        # PostgreSQL parses PASSWORD as a literal; a bound $1 is a syntax error.
        connection.exec_driver_sql(
            "ALTER ROLE merchantos_app PASSWORD " + _pg_quote_literal(password)
        )
        # RDS master is rds_superuser, not SUPERUSER. ALTER NOSUPERUSER/NOBYPASSRLS
        # fails there; CREATE already set those attributes.
    engine.dispose()


def upgrade_head(database_url: str) -> None:
    command.upgrade(_alembic_config(database_url), "head")


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required for migrate")
    app_password = os.environ.get("APP_DB_PASSWORD")
    if app_password:
        ensure_app_role(database_url, app_password)
    upgrade_head(database_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
