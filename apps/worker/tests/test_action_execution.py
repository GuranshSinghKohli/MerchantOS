from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from merchantos_app.actions import ActionService, ApprovalService
from merchantos_db import ActionRepository, CommerceRepository, session_scope
from merchantos_db.commerce import ProductWrite
from merchantos_domain import (
    ActionStatus,
    ActionType,
    IntendedProductChange,
    ShopifyThrottledError,
    TenantContext,
    TransientJobError,
)
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.mutator import FakeShopifyMutator, ProductMutationState
from merchantos_worker.capabilities import ExecutionCapabilities
from merchantos_worker.handlers.execution import handle_action_execute
from merchantos_worker.testing import seed_installed_store
from sqlalchemy.engine import Engine

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def _ctx(view) -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=uuid4(),
            scopes=tuple(view.scopes) + ("write_products",),
        )
    )


def _product(engine, ctx, title: str = "Old") -> str:
    with session_scope(engine) as db:
        pid = CommerceRepository(db).upsert_product(
            ctx,
            ProductWrite(
                shopify_gid="gid://shopify/Product/22",
                title=title,
                status="ACTIVE",
                vendor="Acme",
                product_type="mug",
                tags=["keep"],
                published_at=None,
            ),
        )
        return str(pid)


def _approve(engine, ctx, product_id: UUID, title: str = "New") -> str:
    created = ActionService(engine).propose(
        ctx,
        action_type=ActionType.UPDATE_PRODUCT_TITLE,
        resource_id=product_id,
        intended=IntendedProductChange(title=title),
        rationale="Clearer title",
    )
    ApprovalService(engine).decide(
        ctx, UUID(str(created["action_id"])), "APPROVED", session_bound=True
    )
    return str(created["action_id"])


def test_conflict_and_verification_and_retry(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as db:
        view = seed_installed_store(db, shop="exec-a.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    product_id = _product(postgres, ctx)
    action_id = _approve(postgres, ctx, UUID(product_id))
    mutator = FakeShopifyMutator()
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/22",
            title="Changed by merchant",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,  # type: ignore[arg-type]
        owner="e1",
        encryptor=encryptor,
    )
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.CONFLICT.value

    action_id = _approve(postgres, ctx, UUID(product_id), title="Verified")
    mutator = FakeShopifyMutator(verify_mismatch=True)
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/22",
            title="Old",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,  # type: ignore[arg-type]
        owner="e2",
        encryptor=encryptor,
    )
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.FAILED.value

    action_id = _approve(postgres, ctx, UUID(product_id), title="Retry Title")
    mutator = FakeShopifyMutator(fail_with=ShopifyThrottledError("429"))
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/22",
            title="Old",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    with pytest.raises(TransientJobError):
        handle_action_execute(
            engine=postgres,
            caps=ExecutionCapabilities(mutator=mutator),
            job_id=action_id,  # type: ignore[arg-type]
            owner="e3",
            encryptor=encryptor,
        )
    mutator.fail_with = None
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,  # type: ignore[arg-type]
        owner="e3",
        encryptor=encryptor,
    )
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.COMPLETED.value


def test_expired_action_does_not_mutate(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as db:
        view = seed_installed_store(db, shop="exec-b.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    product_id = _product(postgres, ctx)
    action_id = _approve(postgres, ctx, UUID(product_id), title="Late")
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    mutator = FakeShopifyMutator()
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/22",
            title="Old",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,  # type: ignore[arg-type]
        owner="e4",
        encryptor=encryptor,
    )
    assert mutator.calls == []
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.EXPIRED.value


def test_missing_resource_and_retry_exhaustion(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as db:
        view = seed_installed_store(db, shop="exec-c.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    product_id = _product(postgres, ctx)
    action_id = _approve(postgres, ctx, UUID(product_id), title="Gone")
    mutator = FakeShopifyMutator(missing=True)
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,  # type: ignore[arg-type]
        owner="e5",
        encryptor=encryptor,
    )
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.FAILED.value

    action_id = _approve(postgres, ctx, UUID(product_id), title="Retry Out")
    mutator = FakeShopifyMutator(fail_with=ShopifyThrottledError("429"))
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/22",
            title="Old",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    for owner in ("e6a", "e6a", "e6a"):
        try:
            handle_action_execute(
                engine=postgres,
                caps=ExecutionCapabilities(mutator=mutator),
                job_id=action_id,  # type: ignore[arg-type]
                owner=owner,
                encryptor=encryptor,
            )
        except TransientJobError:
            continue
    with session_scope(postgres) as db:
        row = ActionRepository(db).get(action_id)  # type: ignore[arg-type]
        assert row is not None
        assert row.status == ActionStatus.FAILED.value
        assert row.attempt >= 3
