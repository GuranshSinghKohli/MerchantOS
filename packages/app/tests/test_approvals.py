from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_app.actions import ApprovalService
from merchantos_domain import ForbiddenFactoryError, TenantContext, UnauthorizedError


def test_approval_requires_session_bound_merchant() -> None:
    engine = SimpleNamespace()
    service = ApprovalService(engine)  # type: ignore[arg-type]
    ctx = TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("write_products",),
        )
    )
    with pytest.raises(ForbiddenFactoryError):
        service.decide(ctx, uuid4(), "APPROVED", session_bound=False)
    worker = TenantContext.from_job_row(
        SimpleNamespace(
            merchant_id=ctx.merchant_id,
            store_id=ctx.store_id,
            user_id=None,
            request_id=ctx.request_id,
            scopes=ctx.scopes,
        )
    )
    with pytest.raises(UnauthorizedError):
        service.decide(worker, uuid4(), "APPROVED", session_bound=True)
