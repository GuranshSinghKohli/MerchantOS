from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from merchantos_db.repositories import IdentityRepository, InstallView
from merchantos_domain import InstallationFailedError, InvalidOAuthStateError
from merchantos_observability import get_logger
from merchantos_shopify.constants import INSTALL_SCOPES
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.hmac_verify import (
    verify_oauth_hmac,
    verify_oauth_timestamp,
)
from merchantos_shopify.oauth import authorization_url, new_oauth_state
from merchantos_shopify.port import ShopifyPort
from merchantos_shopify.shop_domain import normalize_shop_domain
from sqlalchemy.orm import Session

logger = get_logger(__name__)

_STATE_TTL = timedelta(minutes=10)


class OAuthService:
    def __init__(
        self,
        *,
        db: Session,
        shopify: ShopifyPort,
        encryptor: TokenEncryptor,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        webhook_callback_uri: str,
        session_ttl: timedelta,
    ) -> None:
        self._db = db
        self._repo = IdentityRepository(db)
        self._shopify = shopify
        self._encryptor = encryptor
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._webhook_callback_uri = webhook_callback_uri
        self._session_ttl = session_ttl

    def start_install(self, shop: str) -> str:
        domain = normalize_shop_domain(shop)
        state = new_oauth_state()
        expires = datetime.now(UTC) + _STATE_TTL
        self._repo.save_oauth_state(state, domain, expires)
        logger.info("oauth_initiated", shop_domain=domain)
        return authorization_url(
            shop=domain,
            client_id=self._client_id,
            redirect_uri=self._redirect_uri,
            state=state,
            scopes=INSTALL_SCOPES,
        )

    def complete_install(
        self,
        query: dict[str, str],
        request_id: UUID,
    ) -> InstallView:
        verify_oauth_hmac(query, self._client_secret)
        verify_oauth_timestamp(query.get("timestamp"))
        shop = normalize_shop_domain(query.get("shop") or "")
        state = query.get("state") or ""
        code = query.get("code") or ""
        if not code:
            raise InstallationFailedError("OAuth callback missing code")
        now = datetime.now(UTC)
        try:
            self._repo.consume_oauth_state(state, shop, now=now)
        except InvalidOAuthStateError:
            logger.warning("oauth_callback_invalid_state", shop_domain=shop)
            raise
        try:
            grant = self._shopify.exchange_code(shop, code)
            info = self._shopify.fetch_shop(shop, grant.access_token)
            if info.myshopify_domain != shop:
                raise InstallationFailedError("Shopify shop identity did not match OAuth shop")
            scopes = (
                tuple(scope.strip() for scope in grant.scope.split(",") if scope.strip())
                or INSTALL_SCOPES
            )
            encrypted = self._encryptor.encrypt(grant.access_token)
            refresh_blob = (
                self._encryptor.encrypt(grant.refresh_token) if grant.refresh_token else None
            )
            view = self._repo.persist_installation(
                shop_info=info,
                encrypted_token=encrypted,
                encrypted_refresh=refresh_blob,
                token_expires_at=grant.expires_at,
                refresh_expires_at=grant.refresh_expires_at,
                scopes=scopes,
                key_version=self._encryptor.key_version,
                session_ttl=now + self._session_ttl,
                request_id=request_id,
            )
            self._shopify.register_app_uninstalled(
                shop, grant.access_token, self._webhook_callback_uri
            )
        except Exception:
            logger.warning("installation_failed", shop_domain=shop)
            raise
        logger.info(
            "installation_success",
            shop_domain=view.myshopify_domain,
            store_id=str(view.store_id),
        )
        return view

    def handle_uninstall(self, shop_domain: str, request_id: str) -> None:
        shop = normalize_shop_domain(shop_domain)
        removed = self._repo.uninstall(shop, TokenEncryptor.tombstone(), request_id)
        logger.info("uninstall_processed", shop_domain=shop, known_install=removed)
