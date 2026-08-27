import hashlib
import json
from typing import Any

from merchantos_db.models import Product
from merchantos_domain import (
    ActionSnapshot,
    ActionType,
    IntendedProductChange,
    InvalidActionError,
)


def _hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _product_state(product: Product) -> dict[str, Any]:
    return {
        "product_id": str(product.id),
        "shopify_gid": product.shopify_gid,
        "title": product.title,
        "description": getattr(product, "description", "") or "",
        "tags": list(product.tags or []),
        "status": product.status,
    }


class SnapshotService:
    """Builds before/after/payload from the projection. The model cannot supply these."""

    def build(
        self,
        *,
        action_type: ActionType,
        product: Product,
        intended: IntendedProductChange,
    ) -> ActionSnapshot:
        before = _product_state(product)
        after = dict(before)
        payload: dict[str, Any] = {"shopify_gid": product.shopify_gid}
        if action_type is ActionType.UPDATE_PRODUCT_TITLE:
            if not intended.title:
                raise InvalidActionError("title is required")
            if intended.title == before["title"]:
                raise InvalidActionError("title is unchanged")
            after["title"] = intended.title
            payload["title"] = intended.title
        elif action_type is ActionType.UPDATE_PRODUCT_DESCRIPTION:
            if intended.description is None:
                raise InvalidActionError("description is required")
            if intended.description == before["description"]:
                raise InvalidActionError("description is unchanged")
            after["description"] = intended.description
            payload["description"] = intended.description
        elif action_type is ActionType.UPDATE_PRODUCT_TAGS:
            if intended.tags is None:
                raise InvalidActionError("tags are required")
            if list(intended.tags) == before["tags"]:
                raise InvalidActionError("tags are unchanged")
            after["tags"] = list(intended.tags)
            payload["tags"] = list(intended.tags)
        elif action_type is ActionType.UPDATE_PRODUCT_STATUS:
            if intended.status is None:
                raise InvalidActionError("status is required")
            if intended.status == before["status"]:
                raise InvalidActionError("status is unchanged")
            after["status"] = intended.status
            payload["status"] = intended.status
        else:
            raise InvalidActionError("action type is not snapshottable")
        return ActionSnapshot(
            before_state=before,
            after_state=after,
            payload=payload,
            payload_hash=_hash(payload),
            affected_count=1,
        )
