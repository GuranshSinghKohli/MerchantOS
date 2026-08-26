from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request
from merchantos_db import IdentityRepository, session_scope
from merchantos_domain import TenantContext, UnauthorizedError

from merchantos_api.deps import db_engine
from merchantos_api.session_cookie import SESSION_COOKIE

router = APIRouter(prefix="/api/v1", tags=["session"])


def _session_id(request: Request) -> UUID:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise UnauthorizedError("not authenticated")
    try:
        return UUID(raw)
    except ValueError as exc:
        raise UnauthorizedError("not authenticated") from exc


@router.get("/me")
def me(request: Request) -> dict[str, object]:
    request_id = UUID(str(request.state.request_id))
    with session_scope(db_engine()) as db:
        repo = IdentityRepository(db)
        identity = repo.get_session(_session_id(request), request_id, now=datetime.now(UTC))
        view = repo.get_install_view(_session_id(request), now=datetime.now(UTC))
        ctx = TenantContext.from_session(identity)
    return {
        "merchant_id": str(ctx.merchant_id),
        "store_id": str(ctx.store_id),
        "user_id": str(ctx.user_id) if ctx.user_id else None,
        "shop_domain": view.myshopify_domain,
        "installed": view.installed,
        "scopes": list(view.scopes),
    }


@router.get("/settings")
def settings_view(request: Request) -> dict[str, object]:
    body = me(request)
    return {
        "connection": "shopify",
        "shop_domain": body["shop_domain"],
        "installed": body["installed"],
        "scopes": body["scopes"],
    }
