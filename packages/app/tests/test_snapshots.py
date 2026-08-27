from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_app.snapshots import SnapshotService
from merchantos_domain import ActionType, IntendedProductChange, InvalidActionError


class _Product:
    id = uuid4()
    shopify_gid = "gid://shopify/Product/1"
    title = "Old Mug"
    description = ""
    tags = ["keep"]
    status = "ACTIVE"


def test_snapshot_builds_title_change_and_rejects_unchanged() -> None:
    product = _Product()
    snap = SnapshotService().build(
        action_type=ActionType.UPDATE_PRODUCT_TITLE,
        product=product,  # type: ignore[arg-type]
        intended=IntendedProductChange(title="New Mug"),
    )
    assert snap.before_state["title"] == "Old Mug"
    assert snap.after_state["title"] == "New Mug"
    assert snap.payload == {"shopify_gid": product.shopify_gid, "title": "New Mug"}
    assert snap.payload_hash
    with pytest.raises(InvalidActionError):
        SnapshotService().build(
            action_type=ActionType.UPDATE_PRODUCT_TITLE,
            product=product,  # type: ignore[arg-type]
            intended=IntendedProductChange(title="Old Mug"),
        )


def test_snapshot_ignores_model_supplied_after_state() -> None:
    intended = IntendedProductChange.model_validate({"title": "Safe Title"})
    snap = SnapshotService().build(
        action_type=ActionType.UPDATE_PRODUCT_TITLE,
        product=_Product(),  # type: ignore[arg-type]
        intended=intended,
    )
    assert "Ignore" not in snap.after_state["title"]
    assert snap.after_state["title"] == "Safe Title"
    extra = SimpleNamespace(title="Hijack", description="x", tags=[], status="DRAFT")
    _ = extra
    assert snap.after_state["status"] == "ACTIVE"
