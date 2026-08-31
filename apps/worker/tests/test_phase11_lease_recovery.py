from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from merchantos_app.actions import ActionService, ApprovalService
from merchantos_db import ActionRepository, CommerceRepository, session_scope
from merchantos_db.commerce import ProductWrite
from merchantos_domain import ActionStatus, ActionType, IntendedProductChange, TenantContext
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


def test_held_lease_blocks_duplicate_execution_then_recovers(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as db:
        view = seed_installed_store(db, shop="lease-a.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
        product_id = CommerceRepository(db).upsert_product(
            ctx,
            ProductWrite(
                shopify_gid="gid://shopify/Product/88",
                title="Old",
                status="ACTIVE",
                vendor="Acme",
                product_type="mug",
                tags=["keep"],
                published_at=None,
            ),
        )
    created = ActionService(postgres).propose(
        ctx,
        action_type=ActionType.UPDATE_PRODUCT_TITLE,
        resource_id=product_id,
        intended=IntendedProductChange(title="New"),
        rationale="Clearer title",
    )
    ApprovalService(postgres).decide(
        ctx, UUID(str(created["action_id"])), "APPROVED", session_bound=True
    )
    action_id = UUID(str(created["action_id"]))
    now = datetime.now(UTC)
    with session_scope(postgres) as db:
        row = ActionRepository(db).acquire_lease(
            action_id, owner="crashed-worker", now=now, ttl=timedelta(seconds=60)
        )
        assert row is not None
        assert row.status == ActionStatus.EXECUTING.value
    mutator = FakeShopifyMutator()
    mutator.seed(
        ProductMutationState(
            shopify_gid="gid://shopify/Product/88",
            title="Old",
            description="",
            tags=("keep",),
            status="ACTIVE",
        )
    )
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,
        owner="replacement",
        encryptor=encryptor,
    )
    assert mutator.calls == []
    with session_scope(postgres) as db:
        held = ActionRepository(db).get(action_id)
        assert held is not None
        assert held.status == ActionStatus.EXECUTING.value
        held.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    handle_action_execute(
        engine=postgres,
        caps=ExecutionCapabilities(mutator=mutator),
        job_id=action_id,
        owner="replacement",
        encryptor=encryptor,
    )
    assert [item[0] for item in mutator.calls] == ["update_product_title"]
    with session_scope(postgres) as db:
        done = ActionRepository(db).get(action_id)
        assert done is not None
        assert done.status == ActionStatus.COMPLETED.value
