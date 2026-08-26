from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request
from merchantos_db import IdentityRepository, session_scope
from merchantos_domain import TenantContext, UnauthorizedError
from sqlalchemy import Engine

from merchantos_api.session_cookie import SESSION_COOKIE


def session_id_from_request(request: Request) -> UUID:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise UnauthorizedError("not authenticated")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise UnauthorizedError("not authenticated") from exc


def tenant_from_request(engine: Engine, request: Request) -> TenantContext:
    request_id = UUID(str(request.state.request_id))
    with session_scope(engine) as db:
        identity = IdentityRepository(db).get_session(
            session_id_from_request(request), request_id, now=datetime.now(UTC)
        )
        return TenantContext.from_session(identity)
