from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from merchantos_domain import InvalidOAuthStateError, UnauthorizedError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from merchantos_db.ids import uuid7
from merchantos_db.models import (
    AuditEvent,
    Merchant,
    MerchantUser,
    OAuthState,
    ShopifyCredential,
    Store,
    WebhookEvent,
)
from merchantos_db.models import (
    Session as SessionRow,
)
from merchantos_db.rls import tenant_scope


@dataclass
class SessionRecord:
    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class InstallView:
    merchant_id: UUID
    store_id: UUID
    user_id: UUID
    session_id: UUID
    shop_domain: str
    myshopify_domain: str
    scopes: tuple[str, ...]
    installed: bool


class IdentityRepository:
    """Persistence for OAuth install, sessions, and uninstall. Privileged for insert."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_oauth_state(self, state: str, shop_domain: str, expires_at: datetime) -> None:
        self._session.add(OAuthState(state=state, shop_domain=shop_domain, expires_at=expires_at))
        self._session.flush()

    def consume_oauth_state(self, state: str, shop_domain: str, *, now: datetime) -> None:
        row = self._session.scalar(select(OAuthState).where(OAuthState.state == state))
        if row is None or row.consumed_at is not None or row.expires_at <= now:
            raise InvalidOAuthStateError("OAuth state is invalid or expired")
        if row.shop_domain != shop_domain:
            raise InvalidOAuthStateError("OAuth state is bound to a different shop")
        row.consumed_at = now
        self._session.flush()

    def persist_installation(
        self,
        *,
        shop_info: object,
        encrypted_token: bytes,
        encrypted_refresh: bytes | None,
        token_expires_at: datetime | None,
        refresh_expires_at: datetime | None,
        scopes: tuple[str, ...],
        key_version: str,
        session_ttl: datetime,
        request_id: UUID,
    ) -> InstallView:
        info = shop_info
        myshopify = info.myshopify_domain  # type: ignore[attr-defined]
        now = datetime.now(UTC)
        store = self._session.scalar(select(Store).where(Store.myshopify_domain == myshopify))
        if store is None:
            merchant = Merchant(id=uuid7(), name=info.name, status="active")  # type: ignore[attr-defined]
            self._session.add(merchant)
            self._session.flush()
            store = Store(
                id=uuid7(),
                merchant_id=merchant.id,
                shop_domain=info.primary_host,  # type: ignore[attr-defined]
                myshopify_domain=myshopify,
                shopify_shop_gid=info.shopify_shop_gid,  # type: ignore[attr-defined]
                currency=info.currency,  # type: ignore[attr-defined]
                iana_timezone=info.iana_timezone,  # type: ignore[attr-defined]
                plan_name=info.plan_name,  # type: ignore[attr-defined]
                installed_at=now,
                uninstalled_at=None,
                sync_status="not_started",
            )
            self._session.add(store)
            self._session.flush()
            user = MerchantUser(
                id=uuid7(),
                merchant_id=merchant.id,
                email=f"owner@{myshopify}",
                role="owner",
            )
            self._session.add(user)
            self._session.flush()
            cred = ShopifyCredential(
                merchant_id=merchant.id,
                store_id=store.id,
                encrypted_offline_token=encrypted_token,
                encrypted_refresh_token=encrypted_refresh,
                token_expires_at=token_expires_at,
                refresh_token_expires_at=refresh_expires_at,
                scopes=list(scopes),
                key_version=key_version,
            )
            self._session.add(cred)
        else:
            existing_merchant = self._session.get(Merchant, store.merchant_id)
            if existing_merchant is None:
                raise RuntimeError("store is missing merchant")
            merchant = existing_merchant
            store.shop_domain = info.primary_host  # type: ignore[attr-defined]
            store.shopify_shop_gid = info.shopify_shop_gid  # type: ignore[attr-defined]
            store.currency = info.currency  # type: ignore[attr-defined]
            store.iana_timezone = info.iana_timezone  # type: ignore[attr-defined]
            store.plan_name = info.plan_name  # type: ignore[attr-defined]
            store.installed_at = now
            store.uninstalled_at = None
            store.sync_status = "not_started"
            found_user = self._session.scalar(
                select(MerchantUser).where(MerchantUser.merchant_id == merchant.id)
            )
            if found_user is None:
                user = MerchantUser(
                    id=uuid7(),
                    merchant_id=merchant.id,
                    email=f"owner@{myshopify}",
                    role="owner",
                )
                self._session.add(user)
                self._session.flush()
            else:
                user = found_user
            found_cred = self._session.scalar(
                select(ShopifyCredential).where(ShopifyCredential.store_id == store.id)
            )
            if found_cred is None:
                self._session.add(
                    ShopifyCredential(
                        merchant_id=merchant.id,
                        store_id=store.id,
                        encrypted_offline_token=encrypted_token,
                        encrypted_refresh_token=encrypted_refresh,
                        token_expires_at=token_expires_at,
                        refresh_token_expires_at=refresh_expires_at,
                        scopes=list(scopes),
                        key_version=key_version,
                    )
                )
            else:
                found_cred.encrypted_offline_token = encrypted_token
                found_cred.encrypted_refresh_token = encrypted_refresh
                found_cred.token_expires_at = token_expires_at
                found_cred.refresh_token_expires_at = refresh_expires_at
                found_cred.scopes = list(scopes)
                found_cred.key_version = key_version
            self._session.execute(
                update(SessionRow)
                .where(SessionRow.store_id == store.id, SessionRow.revoked_at.is_(None))
                .values(revoked_at=now)
            )

        session_row = SessionRow(
            id=uuid7(),
            merchant_id=store.merchant_id,
            user_id=user.id,
            store_id=store.id,
            expires_at=session_ttl,
        )
        self._session.add(session_row)
        self._session.add(
            AuditEvent(
                merchant_id=store.merchant_id,
                actor_type="system",
                request_id=str(request_id),
                event_type="shopify.installed",
                resource_type="store",
                resource_id=str(store.id),
                metadata_json="{}",
            )
        )
        self._session.flush()
        return InstallView(
            merchant_id=store.merchant_id,
            store_id=store.id,
            user_id=user.id,
            session_id=session_row.id,
            shop_domain=store.shop_domain,
            myshopify_domain=store.myshopify_domain,
            scopes=scopes,
            installed=True,
        )

    def get_session(self, session_id: UUID, request_id: UUID, *, now: datetime) -> SessionRecord:
        row = self._session.get(SessionRow, session_id)
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            raise UnauthorizedError("session is missing or expired")
        store = self._session.get(Store, row.store_id)
        if store is None or store.uninstalled_at is not None:
            raise UnauthorizedError("store is not installed")
        cred = self._session.scalar(
            select(ShopifyCredential).where(ShopifyCredential.store_id == row.store_id)
        )
        scopes = tuple(cred.scopes) if cred is not None else ()
        return SessionRecord(
            merchant_id=row.merchant_id,
            store_id=row.store_id,
            user_id=row.user_id,
            request_id=request_id,
            scopes=scopes,
        )

    def get_install_view(self, session_id: UUID, *, now: datetime) -> InstallView:
        row = self._session.get(SessionRow, session_id)
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            raise UnauthorizedError("session is missing or expired")
        store = self._session.get(Store, row.store_id)
        if store is None:
            raise UnauthorizedError("store is missing")
        cred = self._session.scalar(
            select(ShopifyCredential).where(ShopifyCredential.store_id == row.store_id)
        )
        return InstallView(
            merchant_id=row.merchant_id,
            store_id=row.store_id,
            user_id=row.user_id or row.merchant_id,
            session_id=row.id,
            shop_domain=store.shop_domain,
            myshopify_domain=store.myshopify_domain,
            scopes=tuple(cred.scopes) if cred else (),
            installed=store.uninstalled_at is None,
        )

    def uninstall(self, shop_domain: str, tombstone: bytes, request_id: str) -> bool:
        store = self._session.scalar(
            select(Store).where(
                (Store.myshopify_domain == shop_domain) | (Store.shop_domain == shop_domain)
            )
        )
        if store is None:
            return False
        now = datetime.now(UTC)
        store.uninstalled_at = now
        store.sync_status = "uninstalled"
        self._session.execute(
            update(SessionRow)
            .where(SessionRow.store_id == store.id, SessionRow.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        cred = self._session.scalar(
            select(ShopifyCredential).where(ShopifyCredential.store_id == store.id)
        )
        if cred is not None:
            cred.encrypted_offline_token = tombstone
            cred.encrypted_refresh_token = tombstone
        self._session.add(
            AuditEvent(
                merchant_id=store.merchant_id,
                actor_type="webhook",
                request_id=request_id,
                event_type="shopify.uninstalled",
                resource_type="store",
                resource_id=str(store.id),
                metadata_json="{}",
            )
        )
        self._session.flush()
        return True

    def record_webhook(
        self,
        *,
        event_id: str,
        topic: str,
        shop_domain: str,
        payload_hash: str,
        resource_gid: str | None = None,
        payload_json: str = "{}",
    ) -> WebhookEvent | None:
        existing = self._session.scalar(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        if existing is not None:
            return None
        store = self._session.scalar(
            select(Store).where(
                (Store.myshopify_domain == shop_domain) | (Store.shop_domain == shop_domain)
            )
        )
        event = WebhookEvent(
            merchant_id=store.merchant_id if store else None,
            store_id=store.id if store else None,
            topic=topic,
            shop_domain=shop_domain,
            event_id=event_id,
            payload_hash=payload_hash,
            resource_gid=resource_gid,
            payload_json=payload_json,
            status="received",
        )
        self._session.add(event)
        self._session.flush()
        return event

    def load_credential_blob(self, merchant_id: UUID, store_id: UUID) -> bytes | None:
        with tenant_scope(self._session, merchant_id):
            cred = self._session.scalar(
                select(ShopifyCredential).where(
                    ShopifyCredential.merchant_id == merchant_id,
                    ShopifyCredential.store_id == store_id,
                )
            )
        return None if cred is None else cred.encrypted_offline_token
