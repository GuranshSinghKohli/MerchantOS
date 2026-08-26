from datetime import timedelta
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from merchantos_db import session_scope
from merchantos_domain import ConfigurationError, DomainError
from merchantos_shopify.adapter import ShopifyAdapter
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.shop_domain import normalize_shop_domain

from merchantos_api.deps import db_engine, settings
from merchantos_api.oauth_service import OAuthService
from merchantos_api.session_cookie import set_session_cookie

router = APIRouter(prefix="/api/v1/auth/shopify", tags=["auth"])


def _service(db) -> OAuthService:  # type: ignore[no-untyped-def]
    cfg = settings()
    if not cfg.shopify_api_key or not cfg.shopify_api_secret or not cfg.token_encryption_key:
        raise ConfigurationError("Shopify OAuth is not configured")
    return OAuthService(
        db=db,
        shopify=ShopifyAdapter(client_id=cfg.shopify_api_key, client_secret=cfg.shopify_api_secret),
        encryptor=TokenEncryptor.from_urlsafe_key(
            cfg.token_encryption_key, cfg.token_encryption_key_version
        ),
        client_id=cfg.shopify_api_key,
        client_secret=cfg.shopify_api_secret,
        redirect_uri=cfg.shopify_redirect_uri,
        webhook_callback_uri=f"{cfg.api_public_base_url.rstrip('/')}/api/v1/webhooks/shopify/app/uninstalled",
        session_ttl=timedelta(hours=cfg.session_ttl_hours),
    )


@router.get("/install")
def install(shop: str) -> RedirectResponse:
    normalize_shop_domain(shop)
    with session_scope(db_engine()) as db:
        url = _service(db).start_install(shop)
    return RedirectResponse(url, status_code=302)


@router.get("/callback")
def callback(request: Request) -> RedirectResponse:
    cfg = settings()
    query = {key: value for key, value in request.query_params.multi_items()}
    request_id = UUID(str(request.state.request_id))
    try:
        with session_scope(db_engine()) as db:
            view = _service(db).complete_install(query, request_id)
    except DomainError as exc:
        query_err = urlencode({"installed": "0", "reason": str(exc)})
        dest = f"{cfg.web_origin.rstrip('/')}/install?{query_err}"
        return RedirectResponse(dest, status_code=302)
    dest = f"{cfg.web_origin.rstrip('/')}/install?installed=1"
    response = RedirectResponse(dest, status_code=302)
    set_session_cookie(
        response,
        str(view.session_id),
        secure=cfg.app_env != "dev",
        max_age=cfg.session_ttl_hours * 3600,
    )
    return response
