from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from merchantos_db import IdentityRepository, JobRepository, session_scope
from merchantos_db.jobs import SyncJobIdentity
from merchantos_db.models import ShopifyCredential
from merchantos_domain import StoreUninstalledError, TenantContext
from merchantos_shopify.encryption import TokenEncryptor
from sqlalchemy import Engine, select


@dataclass(frozen=True)
class StoreAccess:
    ctx: TenantContext
    shop_domain: str
    access_token: str


def load_store_access(
    engine: Engine,
    *,
    merchant_id: UUID,
    store_id: UUID,
    user_id: UUID | None,
    request_id: UUID,
    encryptor: TokenEncryptor | None,
) -> StoreAccess:
    if encryptor is None:
        raise StoreUninstalledError("token encryption is not configured")
    with session_scope(engine) as db:
        blob = IdentityRepository(db).load_credential_blob(merchant_id, store_id)
        store = JobRepository(db).get_store(store_id)
        cred = db.scalar(
            select(ShopifyCredential).where(
                ShopifyCredential.merchant_id == merchant_id,
                ShopifyCredential.store_id == store_id,
            )
        )
        scopes = tuple(cred.scopes) if cred is not None else ()
        if store is None or store.uninstalled_at is not None or blob is None:
            raise StoreUninstalledError("store is not installed")
        shop = store.myshopify_domain
    token = encryptor.decrypt(blob)
    identity = SyncJobIdentity(
        merchant_id=merchant_id,
        store_id=store_id,
        user_id=user_id,
        request_id=request_id,
        scopes=scopes,
    )
    return StoreAccess(
        ctx=TenantContext.from_job_row(identity),
        shop_domain=shop,
        access_token=token,
    )
