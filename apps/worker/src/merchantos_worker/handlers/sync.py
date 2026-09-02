from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from merchantos_db import CommerceRepository, JobRepository, session_scope
from merchantos_domain import TenantContext, TransientJobError
from merchantos_observability import get_logger
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.reader import (
    CustomerRecord,
    InventoryRecord,
    LocationRecord,
    OrderRecord,
    Page,
    ProductRecord,
    ShopifyReader,
)
from sqlalchemy import Engine

from merchantos_worker.credentials import load_store_access
from merchantos_worker.projection import (
    apply_customer,
    apply_inventory,
    apply_location,
    apply_order,
    apply_product,
    incremental_query,
)

logger = get_logger(__name__)
_LEASE = timedelta(minutes=5)
_PAGE_SIZE = 50


def handle_sync(
    *,
    engine: Engine,
    reader: ShopifyReader,
    encryptor: TokenEncryptor | None,
    job_id: UUID,
    owner: str,
) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as db:
        jobs = JobRepository(db)
        job = jobs.acquire_sync_lease(job_id, owner=owner, now=now, ttl=_LEASE)
        if job is None:
            return
        merchant_id = job.merchant_id
        store_id = job.store_id
        user_id = job.user_id
        request_id = job.request_id
        resource = job.resource
        kind = job.kind
        cursor = job.cursor
        processed = job.records_processed
        failed = job.records_failed
        store = jobs.get_store(store_id)
        since = store.last_synced_at if store is not None else None

    try:
        access = load_store_access(
            engine,
            merchant_id=merchant_id,
            store_id=store_id,
            user_id=user_id,
            request_id=request_id,
            encryptor=encryptor,
        )
        query = incremental_query(since) if kind == "incremental" else None
        captured_at = now.replace(microsecond=0)
        while True:
            page = _fetch_page(
                reader,
                resource,
                access.shop_domain,
                access.access_token,
                after=cursor,
                query=query,
            )
            with session_scope(engine) as db:
                commerce = CommerceRepository(db)
                for item in page.items:
                    try:
                        if not _apply_item(commerce, access.ctx, resource, item, captured_at):
                            failed += 1
                            logger.warning(
                                "sync_record_skipped",
                                resource=resource,
                                job_id=str(job_id),
                            )
                            continue
                        processed += 1
                    except TransientJobError:
                        raise
                    except Exception as exc:
                        failed += 1
                        logger.warning(
                            "sync_record_failed",
                            resource=resource,
                            job_id=str(job_id),
                            error_type=type(exc).__name__,
                        )
                JobRepository(db).update_sync_progress(
                    job_id,
                    cursor=page.end_cursor,
                    records_processed=processed,
                    records_failed=failed,
                )
            if not page.has_next:
                break
            cursor = page.end_cursor
        with session_scope(engine) as db:
            JobRepository(db).complete_sync(job_id, now=datetime.now(UTC))
        logger.info(
            "sync_completed",
            job_id=str(job_id),
            store_id=str(store_id),
            resource=resource,
            records_processed=processed,
            records_failed=failed,
            retries=getattr(reader, "last_retries", 0),
        )
    except TransientJobError:
        raise
    except Exception as exc:
        with session_scope(engine) as db:
            JobRepository(db).fail_sync(job_id, error=type(exc).__name__, now=datetime.now(UTC))
        logger.warning(
            "sync_failed",
            job_id=str(job_id),
            error_type=type(exc).__name__,
            error_detail=str(exc)[:120],
        )


def _fetch_page(
    reader: ShopifyReader,
    resource: str,
    shop: str,
    token: str,
    *,
    after: str | None,
    query: str | None,
) -> Page[Any]:
    first = _PAGE_SIZE
    if resource == "products":
        return reader.fetch_products_page(shop, token, after=after, query=query, first=first)
    if resource == "orders":
        return reader.fetch_orders_page(shop, token, after=after, query=query, first=first)
    if resource == "customers":
        return reader.fetch_customers_page(shop, token, after=after, query=query, first=first)
    if resource == "locations":
        return reader.fetch_locations_page(shop, token, after=after, first=first)
    if resource == "inventory":
        return reader.fetch_inventory_page(shop, token, after=after, first=first)
    raise TransientJobError(f"unknown sync resource {resource}")


def _apply_item(
    commerce: CommerceRepository,
    ctx: TenantContext,
    resource: str,
    item: object,
    captured_at: datetime,
) -> bool:
    if resource == "products" and isinstance(item, ProductRecord):
        apply_product(commerce, ctx, item)
        return True
    if resource == "orders" and isinstance(item, OrderRecord):
        apply_order(commerce, ctx, item)
        return True
    if resource == "customers" and isinstance(item, CustomerRecord):
        apply_customer(commerce, ctx, item)
        return True
    if resource == "locations" and isinstance(item, LocationRecord):
        apply_location(commerce, ctx, item)
        return True
    if resource == "inventory" and isinstance(item, InventoryRecord):
        return apply_inventory(commerce, ctx, item, captured_at)
    raise ValueError("unexpected sync item")
