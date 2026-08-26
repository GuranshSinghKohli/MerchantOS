from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from merchantos_db import CommerceRepository, JobRepository, session_scope
from merchantos_db.jobs import SyncJobIdentity
from merchantos_domain import TenantContext
from merchantos_observability import get_logger
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.reader import InventoryRecord, ShopifyReader
from sqlalchemy import Engine

from merchantos_worker.credentials import load_store_access
from merchantos_worker.projection import (
    apply_customer,
    apply_inventory,
    apply_location,
    apply_order,
    apply_product,
)

logger = get_logger(__name__)


def handle_webhook(
    *,
    engine: Engine,
    reader: ShopifyReader,
    encryptor: TokenEncryptor | None,
    job_id: UUID,
) -> None:
    with session_scope(engine) as db:
        event = JobRepository(db).get_webhook(job_id)
        if event is None:
            return
        if event.status == "processed":
            return
        if event.merchant_id is None or event.store_id is None:
            JobRepository(db).mark_webhook_status(job_id, "ignored")
            return
        merchant_id = event.merchant_id
        store_id = event.store_id
        topic = event.topic
        resource_gid = event.resource_gid
        payload_json = event.payload_json
        request_id = event.id

    if topic.endswith("/delete") or topic.endswith("/redact"):
        identity = SyncJobIdentity(
            merchant_id=merchant_id,
            store_id=store_id,
            user_id=None,
            request_id=request_id,
            scopes=(),
        )
        ctx = TenantContext.from_job_row(identity)
        _apply_delete(engine, ctx, topic, resource_gid)
        with session_scope(engine) as db:
            JobRepository(db).mark_webhook_status(job_id, "processed")
        logger.info("webhook_processed", topic=topic, job_id=str(job_id), mode="delete")
        return

    access = load_store_access(
        engine,
        merchant_id=merchant_id,
        store_id=store_id,
        user_id=None,
        request_id=request_id,
        encryptor=encryptor,
    )
    _apply_upsert(
        engine,
        reader,
        access.shop_domain,
        access.access_token,
        access.ctx,
        topic,
        resource_gid,
        payload_json,
    )
    with session_scope(engine) as db:
        JobRepository(db).mark_webhook_status(job_id, "processed")
    logger.info("webhook_processed", topic=topic, job_id=str(job_id), mode="async")


def _apply_delete(engine: Engine, ctx: TenantContext, topic: str, gid: str | None) -> None:
    if not gid:
        return
    now = datetime.now(UTC)
    with session_scope(engine) as db:
        commerce = CommerceRepository(db)
        if topic.startswith("products/"):
            commerce.mark_product_deleted(ctx, gid, now)
        elif topic.startswith("customers/"):
            commerce.mark_customer_deleted(ctx, gid, now)


def _apply_upsert(
    engine: Engine,
    reader: ShopifyReader,
    shop: str,
    token: str,
    ctx: TenantContext,
    topic: str,
    gid: str | None,
    payload_json: str,
) -> None:
    captured_at = datetime.now(UTC).replace(microsecond=0)
    with session_scope(engine) as db:
        commerce = CommerceRepository(db)
        if topic.startswith("products/") and gid:
            product = reader.fetch_product(shop, token, gid)
            if product is not None:
                apply_product(commerce, ctx, product)
            return
        if topic.startswith("orders/") and gid:
            order = reader.fetch_order(shop, token, gid)
            if order is not None:
                apply_order(commerce, ctx, order)
            return
        if topic.startswith("customers/") and gid:
            customer = reader.fetch_customer(shop, token, gid)
            if customer is not None:
                apply_customer(commerce, ctx, customer)
            return
        if topic.startswith("locations/") and gid:
            location = reader.fetch_location(shop, token, gid)
            if location is not None:
                apply_location(commerce, ctx, location)
            return
        if topic.startswith("inventory_levels"):
            ref = json.loads(payload_json or "{}")
            item_gid = ref.get("inventory_item_gid")
            loc_gid = ref.get("location_gid")
            available = ref.get("available")
            if not isinstance(item_gid, str) or not isinstance(loc_gid, str):
                return
            variant_gid = commerce.get_variant_gid_by_inventory_item(ctx, item_gid)
            if variant_gid is None:
                return
            on_hand = available if isinstance(available, int) else 0
            apply_inventory(
                commerce,
                ctx,
                InventoryRecord(
                    variant_gid=variant_gid,
                    inventory_item_gid=item_gid,
                    location_gid=loc_gid,
                    available=on_hand if isinstance(available, int) else 0,
                    on_hand=on_hand,
                ),
                captured_at,
            )
