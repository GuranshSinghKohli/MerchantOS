from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from merchantos_domain import InvalidActionError

from merchantos_shopify.adapter import ShopifyAdapter

PRODUCT_GET = """
query ProductNode($id: ID!) {
  product(id: $id) {
    id
    title
    status
    tags
    descriptionHtml
  }
}
"""

PRODUCT_UPDATE = """
mutation ProductUpdate($product: ProductUpdateInput!) {
  productUpdate(product: $product) {
    product {
      id
      title
      status
      tags
      descriptionHtml
    }
    userErrors { field message }
  }
}
"""


@dataclass(frozen=True)
class ProductMutationState:
    shopify_gid: str
    title: str
    description: str
    tags: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class MutationOutcome:
    ok: bool
    request_id: str | None
    state: ProductMutationState | None
    error_code: str | None = None
    user_errors: tuple[str, ...] = ()


class ShopifyMutator(Protocol):
    """Allowlisted product mutations only. No generic GraphQL/HTTP entry."""

    def get_product(
        self, shop: str, access_token: str, product_gid: str
    ) -> ProductMutationState: ...

    def update_product_title(
        self, shop: str, access_token: str, product_gid: str, title: str
    ) -> MutationOutcome: ...

    def update_product_description(
        self, shop: str, access_token: str, product_gid: str, description: str
    ) -> MutationOutcome: ...

    def update_product_tags(
        self, shop: str, access_token: str, product_gid: str, tags: list[str]
    ) -> MutationOutcome: ...

    def update_product_status(
        self, shop: str, access_token: str, product_gid: str, status: str
    ) -> MutationOutcome: ...


def _state_from_node(node: dict[str, Any]) -> ProductMutationState:
    tags_raw = node.get("tags")
    tags = tuple(str(item) for item in tags_raw) if isinstance(tags_raw, list) else ()
    return ProductMutationState(
        shopify_gid=str(node.get("id") or ""),
        title=str(node.get("title") or ""),
        description=str(node.get("descriptionHtml") or ""),
        tags=tags,
        status=str(node.get("status") or ""),
    )


class AdapterShopifyMutator:
    """Typed productUpdate wrappers. There is no generic execute method."""

    def __init__(self, adapter: ShopifyAdapter) -> None:
        self._adapter = adapter

    def get_product(self, shop: str, access_token: str, product_gid: str) -> ProductMutationState:
        data = self._adapter._graphql(shop, access_token, PRODUCT_GET, {"id": product_gid})
        node = (data.get("data") or {}).get("product")
        if not isinstance(node, dict) or not node.get("id"):
            raise InvalidActionError("product not found on Shopify")
        return _state_from_node(node)

    def _update(self, shop: str, access_token: str, product: dict[str, Any]) -> MutationOutcome:
        data = self._adapter._graphql(shop, access_token, PRODUCT_UPDATE, {"product": product})
        payload = (data.get("data") or {}).get("productUpdate") or {}
        errors = payload.get("userErrors") or []
        if errors:
            messages = tuple(str(item.get("message") or "user_error") for item in errors)
            return MutationOutcome(
                ok=False,
                request_id=None,
                state=None,
                error_code="user_error",
                user_errors=messages,
            )
        node = payload.get("product")
        if not isinstance(node, dict):
            return MutationOutcome(
                ok=False, request_id=None, state=None, error_code="empty_mutation"
            )
        return MutationOutcome(ok=True, request_id=None, state=_state_from_node(node))

    def update_product_title(
        self, shop: str, access_token: str, product_gid: str, title: str
    ) -> MutationOutcome:
        return self._update(shop, access_token, {"id": product_gid, "title": title})

    def update_product_description(
        self, shop: str, access_token: str, product_gid: str, description: str
    ) -> MutationOutcome:
        return self._update(shop, access_token, {"id": product_gid, "descriptionHtml": description})

    def update_product_tags(
        self, shop: str, access_token: str, product_gid: str, tags: list[str]
    ) -> MutationOutcome:
        return self._update(shop, access_token, {"id": product_gid, "tags": tags})

    def update_product_status(
        self, shop: str, access_token: str, product_gid: str, status: str
    ) -> MutationOutcome:
        if status not in {"ACTIVE", "DRAFT"}:
            raise InvalidActionError("status is not safely supported")
        return self._update(shop, access_token, {"id": product_gid, "status": status})


@dataclass
class FakeShopifyMutator:
    products: dict[str, ProductMutationState] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail_with: Exception | None = None
    verify_mismatch: bool = False
    missing: bool = False

    def seed(self, state: ProductMutationState) -> None:
        self.products[state.shopify_gid] = state

    def get_product(self, shop: str, access_token: str, product_gid: str) -> ProductMutationState:
        _ = shop, access_token
        if self.missing:
            raise InvalidActionError("product not found on Shopify")
        found = self.products.get(product_gid)
        if found is None:
            raise InvalidActionError("product not found on Shopify")
        return found

    def _apply(self, name: str, product_gid: str, **updates: object) -> MutationOutcome:
        self.calls.append((name, product_gid))
        if self.fail_with is not None:
            raise self.fail_with
        current = self.products.get(product_gid)
        if current is None:
            raise InvalidActionError("product not found on Shopify")
        updated = ProductMutationState(
            shopify_gid=current.shopify_gid,
            title=str(updates.get("title", current.title)),
            description=str(updates.get("description", current.description)),
            tags=tuple(updates["tags"]) if "tags" in updates else current.tags,  # type: ignore[arg-type]
            status=str(updates.get("status", current.status)),
        )
        if not self.verify_mismatch:
            self.products[product_gid] = updated
        return MutationOutcome(ok=True, request_id="gid://shopify/Request/1", state=updated)

    def update_product_title(
        self, shop: str, access_token: str, product_gid: str, title: str
    ) -> MutationOutcome:
        _ = shop, access_token
        return self._apply("update_product_title", product_gid, title=title)

    def update_product_description(
        self, shop: str, access_token: str, product_gid: str, description: str
    ) -> MutationOutcome:
        _ = shop, access_token
        return self._apply("update_product_description", product_gid, description=description)

    def update_product_tags(
        self, shop: str, access_token: str, product_gid: str, tags: list[str]
    ) -> MutationOutcome:
        _ = shop, access_token
        return self._apply("update_product_tags", product_gid, tags=tuple(tags))

    def update_product_status(
        self, shop: str, access_token: str, product_gid: str, status: str
    ) -> MutationOutcome:
        _ = shop, access_token
        if status not in {"ACTIVE", "DRAFT"}:
            raise InvalidActionError("status is not safely supported")
        return self._apply("update_product_status", product_gid, status=status)


def assert_no_generic_execute(mutator: object) -> None:
    for name in ("execute", "request", "graphql", "raw"):
        if hasattr(mutator, name) and name != "_adapter":
            raise AssertionError(f"generic method {name} must not exist")
