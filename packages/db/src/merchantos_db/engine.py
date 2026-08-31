import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url: str) -> str:
    """Force the psycopg3 driver. Bare postgresql:// defaults to missing psycopg2.

    RDS requires TLS. Local Compose does not. Only production (ECS APP_ENV)
    adds sslmode=require when the URL omitted it.
    """
    if not database_url.startswith("postgresql"):
        raise ValueError("DATABASE_URL must be a PostgreSQL URL")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if "sslmode=" not in database_url and os.environ.get("APP_ENV") == "production":
        joiner = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{joiner}sslmode=require"
    return database_url


def create_db_engine(database_url: str, *, echo: bool = False) -> Engine:
    database_url = normalize_database_url(database_url)
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def ping_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


@contextmanager
def session_scope(engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
