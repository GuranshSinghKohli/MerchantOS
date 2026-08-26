from collections.abc import Generator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@contextmanager
def tenant_scope(session: Session, merchant_id: UUID) -> Generator[None, None, None]:
    """Defense-in-depth RLS. Repositories still filter by merchant_id in SQL.

    FORCE RLS applies this GUC to non-superuser, non-BYPASSRLS roles
    (``merchantos_app``). The Compose owner role is a superuser and still
    bypasses policies; see ADR 0018.
    """
    session.execute(
        text("SELECT set_config('app.current_merchant_id', :mid, true)"),
        {"mid": str(merchant_id)},
    )
    yield
