from __future__ import annotations

import os
from uuid import uuid4

import pytest
from merchantos_db import CommerceRepository, JobRepository, session_scope
from merchantos_domain import TenantContext, TransientJobError
from merchantos_queue import create_queue
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.mutator import FakeShopifyMutator
from merchantos_shopify.testing import FakeShopifyReader, sample_product
from merchantos_worker.capabilities import (
    ExecutionCapabilities,
    SyncCapabilities,
    WebhookCapabilities,
    WorkerRuntime,
    fake_agent_capabilities,
)
from merchantos_worker.dispatch import process_once
from merchantos_worker.handlers.sync import handle_sync
from merchantos_worker.testing import seed_installed_store
from sqlalchemy.exc import IntegrityError

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

pytestmark = pytest.mark.integration


def _encryptor() -> TokenEncryptor:
    return TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")


def _ctx(view, request_id=None) -> TenantContext:
    from types import SimpleNamespace

    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=request_id or uuid4(),
            scopes=view.scopes,
        )
    )


def _runtime(engine, reader, queue) -> WorkerRuntime:
    return WorkerRuntime(
        engine=engine,
        queue=queue,
        sync=SyncCapabilities(reader=reader),
        webhook=WebhookCapabilities(reader=reader),
        agent=fake_agent_capabilities(),
        execution=ExecutionCapabilities(mutator=FakeShopifyMutator()),
        encryptor=_encryptor(),
        owner="test-worker",
    )


def _enqueue_and_run(engine, view, reader, queue) -> None:
    ctx = _ctx(view)
    with session_scope(engine) as db:
        JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="initial")
    runtime = _runtime(engine, reader, queue)
    for _ in range(20):
        process_once(runtime)


def test_full_catalog_sync_and_idempotent_rerun(postgres) -> None:
    engine = postgres
    encryptor = _encryptor()
    reader = FakeShopifyReader()
    reader.page_size = 1
    queue = create_queue(
        endpoint_url=os.environ.get("SQS_ENDPOINT_URL"),
        queue_name=f"sync-{uuid4().hex[:8]}",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="acme.myshopify.com", encryptor=encryptor)
    _enqueue_and_run(engine, view, reader, queue)
    ctx = _ctx(view)
    with session_scope(engine) as db:
        commerce = CommerceRepository(db)
        products = commerce.list_products(ctx)
        variants = commerce.list_variants(ctx)
        orders = commerce.list_orders(ctx)
        lines = commerce.list_order_lines(ctx)
        customers = commerce.list_customers(ctx)
        inventory = commerce.list_inventory(ctx)
        jobs = JobRepository(db).list_sync_jobs(ctx)
        store = JobRepository(db).get_store(view.store_id)
        assert len(products) == 2
        assert len(variants) == 2
        assert len(orders) == 1
        assert len(lines) == 1
        assert any(row.email == "c1@example.com" for row in customers)
        assert inventory[0].available == 7
        assert inventory[0].on_hand == 9
        assert store is not None
        assert store.sync_status == "completed"
        assert {job.status for job in jobs} == {"completed"}

    _enqueue_and_run(engine, view, reader, queue)
    with session_scope(engine) as db:
        commerce = CommerceRepository(db)
        assert len(commerce.list_products(ctx)) == 2
        assert len(commerce.list_variants(ctx)) == 2
        assert len(commerce.list_orders(ctx)) == 1
        assert len(commerce.list_order_lines(ctx)) == 1


def test_pagination_walks_multiple_pages(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    reader.products = [sample_product(i) for i in range(1, 4)]
    reader.page_size = 1
    queue = create_queue(
        endpoint_url=None,
        queue_name="mem",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="page.myshopify.com", encryptor=_encryptor())
    _enqueue_and_run(engine, view, reader, queue)
    ctx = _ctx(view)
    with session_scope(engine) as db:
        assert len(CommerceRepository(db).list_products(ctx)) == 3
    assert reader.calls >= 3


def test_partial_record_failure_keeps_successes(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    reader.inject_bad_item = True
    queue = create_queue(
        endpoint_url=None,
        queue_name="mem",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="partial.myshopify.com", encryptor=_encryptor())
    _enqueue_and_run(engine, view, reader, queue)
    ctx = _ctx(view)
    with session_scope(engine) as db:
        products = CommerceRepository(db).list_products(ctx)
        jobs = [job for job in JobRepository(db).list_sync_jobs(ctx) if job.resource == "products"]
        assert len(products) == 2
        assert jobs[0].records_failed >= 1
        assert jobs[0].status == "completed"


def test_resource_failure_does_not_corrupt_other_resources(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    reader.fail_resource = "orders"
    queue = create_queue(
        endpoint_url=None,
        queue_name="mem",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="fail.myshopify.com", encryptor=_encryptor())
    _enqueue_and_run(engine, view, reader, queue)
    ctx = _ctx(view)
    with session_scope(engine) as db:
        assert CommerceRepository(db).list_products(ctx)
        assert CommerceRepository(db).list_orders(ctx) == []
        order_jobs = [
            job for job in JobRepository(db).list_sync_jobs(ctx) if job.resource == "orders"
        ]
        assert order_jobs[0].status == "failed"
        store = JobRepository(db).get_store(view.store_id)
        assert store is not None
        assert store.sync_status == "failed"


def test_retry_then_success(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    reader.transient_remaining = 1
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="retry.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="retry")
        loc_job = next(job for job in jobs if job.resource == "locations")
    with pytest.raises(TransientJobError):
        handle_sync(
            engine=engine,
            reader=reader,
            encryptor=_encryptor(),
            job_id=loc_job.id,
            owner="retry",
        )
    handle_sync(
        engine=engine,
        reader=reader,
        encryptor=_encryptor(),
        job_id=loc_job.id,
        owner="retry",
    )
    with session_scope(engine) as db:
        job = JobRepository(db).get_sync_job(loc_job.id)
        assert job is not None
        assert job.status == "completed"
        assert job.attempt >= 2


def test_rate_limit_retry(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    reader.throttle_remaining = 1
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="throttle.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="th")
        loc_job = next(job for job in jobs if job.resource == "locations")
    with pytest.raises(TransientJobError):
        handle_sync(
            engine=engine,
            reader=reader,
            encryptor=_encryptor(),
            job_id=loc_job.id,
            owner="th",
        )
    handle_sync(
        engine=engine,
        reader=reader,
        encryptor=_encryptor(),
        job_id=loc_job.id,
        owner="th",
    )
    with session_scope(engine) as db:
        job = JobRepository(db).get_sync_job(loc_job.id)
        assert job is not None
        assert job.status == "completed"


def test_tenant_isolation(postgres) -> None:
    engine = postgres
    encryptor = _encryptor()
    queue = create_queue(
        endpoint_url=None,
        queue_name="mem",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    with session_scope(engine) as db:
        a = seed_installed_store(db, shop="a.myshopify.com", encryptor=encryptor)
        b = seed_installed_store(db, shop="b.myshopify.com", encryptor=encryptor)
    _enqueue_and_run(engine, a, FakeShopifyReader(), queue)
    _enqueue_and_run(engine, b, FakeShopifyReader(), queue)
    ctx_a = _ctx(a)
    ctx_b = _ctx(b)
    with session_scope(engine) as db:
        commerce = CommerceRepository(db)
        a_products = commerce.list_products(ctx_a)
        b_products = commerce.list_products(ctx_b)
        assert a_products
        assert b_products
        assert commerce.get_product(ctx_a, a_products[0].shopify_gid) is not None
        assert all(row.merchant_id == a.merchant_id for row in a_products)
        assert all(row.merchant_id == b.merchant_id for row in b_products)


def test_variant_requires_product_fk(postgres) -> None:
    engine = postgres
    from merchantos_db.ids import uuid7
    from merchantos_db.models import Variant
    from sqlalchemy.orm import Session

    session = Session(engine)
    try:
        view = seed_installed_store(session, shop="fk.myshopify.com", encryptor=_encryptor())
        session.flush()
        session.add(
            Variant(
                id=uuid7(),
                merchant_id=view.merchant_id,
                store_id=view.store_id,
                product_id=uuid7(),
                shopify_gid="gid://shopify/ProductVariant/x",
                title="x",
                price=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
    finally:
        session.rollback()
        session.close()


def test_handle_sync_direct_uses_job_row_tenant(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="direct.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="d")
        job_id = next(job.id for job in jobs if job.resource == "locations")
    handle_sync(
        engine=engine,
        reader=reader,
        encryptor=_encryptor(),
        job_id=job_id,
        owner="direct",
    )
    with session_scope(engine) as db:
        job = JobRepository(db).get_sync_job(job_id)
        assert job is not None
        assert job.status == "completed"


def test_inventory_skips_missing_variant_instead_of_retrying(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="inv-skip.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="is")
        job_id = next(job.id for job in jobs if job.resource == "inventory")
    handle_sync(
        engine=engine,
        reader=reader,
        encryptor=_encryptor(),
        job_id=job_id,
        owner="inv-skip",
    )
    with session_scope(engine) as db:
        job = JobRepository(db).get_sync_job(job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.records_processed == 0
        assert job.records_failed >= 1


def test_missing_encryptor_fails_job_instead_of_hanging(postgres) -> None:
    engine = postgres
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="no-key.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="nk")
        job_id = next(job.id for job in jobs if job.resource == "locations")
    handle_sync(
        engine=engine,
        reader=FakeShopifyReader(),
        encryptor=None,
        job_id=job_id,
        owner="no-key",
    )
    with session_scope(engine) as db:
        job = JobRepository(db).get_sync_job(job_id)
        store = JobRepository(db).get_store(view.store_id)
        assert job is not None
        assert job.status == "failed"
        assert store is not None
        # Sibling resources are still queued; store stays running until they finish.
        assert store.sync_status == "running"
        assert store.sync_error is not None


def test_stale_open_jobs_are_failed_so_import_can_restart(postgres) -> None:
    engine = postgres
    from datetime import UTC, datetime, timedelta

    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="stale.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="st")
        old = datetime.now(UTC) - timedelta(hours=2)
        for job in jobs:
            job.created_at = old
            job.started_at = old
            job.status = "running"
        store = JobRepository(db).get_store(view.store_id)
        assert store is not None
        store.sync_status = "running"
    with session_scope(engine) as db:
        ctx = _ctx(view)
        n = JobRepository(db).fail_stale_open_syncs(ctx, now=datetime.now(UTC))
        assert n == 5
        again = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="st2")
        assert len(again) == 5
        assert {job.status for job in again} == {"pending"}


def test_reenqueue_republishes_open_jobs(postgres) -> None:
    engine = postgres
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="repub.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        first = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="rp")
        first_ids = {job.id for job in first}
        after_first = len(JobRepository(db).unpublished_outbox())
        again = JobRepository(db).enqueue_sync(ctx, kind="initial", idempotency_prefix="rp")
        assert {job.id for job in again} == first_ids
        after_second = JobRepository(db).unpublished_outbox()
        assert len(after_second) == after_first + len(first)
        assert first_ids <= {row.job_id for row in after_second}


def test_transient_error_type() -> None:
    with pytest.raises(TransientJobError):
        raise TransientJobError("x")


def test_incremental_uses_updated_at_query(postgres) -> None:
    engine = postgres
    reader = FakeShopifyReader()
    with session_scope(engine) as db:
        view = seed_installed_store(db, shop="incr.myshopify.com", encryptor=_encryptor())
        ctx = _ctx(view)
        store = JobRepository(db).get_store(view.store_id)
        assert store is not None
        from datetime import UTC, datetime

        store.last_synced_at = datetime(2026, 8, 1, tzinfo=UTC)
        jobs = JobRepository(db).enqueue_sync(ctx, kind="incremental", idempotency_prefix="inc")
        job_id = next(job.id for job in jobs if job.resource == "products")
    handle_sync(
        engine=engine,
        reader=reader,
        encryptor=_encryptor(),
        job_id=job_id,
        owner="inc",
    )
    assert reader.last_query == "updated_at:>'2026-08-01T00:00:00Z'"
