from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from merchantos_shopify.reader import (
    CustomerRecord,
    InventoryRecord,
    LocationRecord,
    OrderLineRecord,
    OrderRecord,
    Page,
    ProductRecord,
    VariantRecord,
)


def parse_money(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        from datetime import UTC

        return parsed.replace(tzinfo=UTC)
    return parsed


def _money_set(node: object) -> Decimal:
    if not isinstance(node, dict):
        return Decimal("0.00")
    shop = node.get("shopMoney")
    if isinstance(shop, dict):
        return parse_money(shop.get("amount"))
    return parse_money(node.get("amount"))


def _edges(connection: object) -> list[dict[str, Any]]:
    if not isinstance(connection, dict):
        return []
    edges = connection.get("edges")
    if not isinstance(edges, list):
        return []
    out: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        node = edge.get("node")
        if isinstance(node, dict):
            out.append(node)
    return out


def page_info(connection: object) -> tuple[bool, str | None]:
    if not isinstance(connection, dict):
        return False, None
    info = connection.get("pageInfo")
    if not isinstance(info, dict):
        return False, None
    end = info.get("endCursor")
    return bool(info.get("hasNextPage")), end if isinstance(end, str) else None


def parse_variant(node: dict[str, Any]) -> VariantRecord:
    item = node.get("inventoryItem")
    item_dict = item if isinstance(item, dict) else {}
    cost_node = item_dict.get("unitCost")
    cost_amount = None
    if isinstance(cost_node, dict):
        cost_amount = parse_money(cost_node.get("amount"))
    item_id = item_dict.get("id")
    compare = node.get("compareAtPrice")
    return VariantRecord(
        shopify_gid=str(node.get("id") or ""),
        title=str(node.get("title") or ""),
        sku=str(node["sku"]) if isinstance(node.get("sku"), str) else None,
        price=parse_money(node.get("price")),
        compare_at_price=parse_money(compare) if compare not in (None, "") else None,
        cost=cost_amount,
        inventory_item_gid=str(item_id) if isinstance(item_id, str) else None,
    )


def parse_product(node: dict[str, Any]) -> ProductRecord:
    tags_raw = node.get("tags")
    tags = tuple(str(tag) for tag in tags_raw) if isinstance(tags_raw, list) else ()
    return ProductRecord(
        shopify_gid=str(node.get("id") or ""),
        title=str(node.get("title") or ""),
        status=str(node.get("status") or ""),
        vendor=str(node.get("vendor") or ""),
        product_type=str(node.get("productType") or ""),
        tags=tags,
        published_at=parse_dt(node.get("publishedAt")),
        variants=tuple(parse_variant(item) for item in _edges(node.get("variants"))),
    )


def parse_order(node: dict[str, Any]) -> OrderRecord:
    customer = node.get("customer")
    customer_gid = None
    if isinstance(customer, dict) and isinstance(customer.get("id"), str):
        customer_gid = str(customer["id"])
    lines: list[OrderLineRecord] = []
    for item in _edges(node.get("lineItems")):
        variant = item.get("variant")
        variant_gid = None
        if isinstance(variant, dict) and isinstance(variant.get("id"), str):
            variant_gid = str(variant["id"])
        lines.append(
            OrderLineRecord(
                shopify_gid=str(item.get("id") or ""),
                variant_gid=variant_gid,
                quantity=int(item.get("quantity") or 0),
                price=_money_set(item.get("originalUnitPriceSet")),
                discount_allocation=_money_set(item.get("totalDiscountSet")),
            )
        )
    currency_node = node.get("totalPriceSet")
    currency = "USD"
    if isinstance(currency_node, dict):
        shop = currency_node.get("shopMoney")
        if isinstance(shop, dict) and isinstance(shop.get("currencyCode"), str):
            currency = str(shop["currencyCode"])
    if isinstance(node.get("currencyCode"), str):
        currency = str(node["currencyCode"])
    return OrderRecord(
        shopify_gid=str(node.get("id") or ""),
        name=str(node.get("name") or ""),
        processed_at=parse_dt(node.get("processedAt")),
        cancelled_at=parse_dt(node.get("cancelledAt")),
        financial_status=str(node.get("displayFinancialStatus") or ""),
        fulfillment_status=str(node.get("displayFulfillmentStatus") or ""),
        currency=currency[:3],
        subtotal=_money_set(node.get("subtotalPriceSet")),
        total_discounts=_money_set(node.get("totalDiscountsSet")),
        total_price=_money_set(node.get("totalPriceSet")),
        customer_gid=customer_gid,
        lines=tuple(lines),
    )


def parse_customer(node: dict[str, Any]) -> CustomerRecord:
    email = ""
    default_email = node.get("defaultEmailAddress")
    if isinstance(default_email, dict) and isinstance(default_email.get("emailAddress"), str):
        email = str(default_email["emailAddress"])
    elif isinstance(node.get("email"), str):
        email = str(node["email"])
    spent = node.get("amountSpent")
    return CustomerRecord(
        shopify_gid=str(node.get("id") or ""),
        email=email,
        orders_count=int(node.get("numberOfOrders") or 0),
        total_spent=_money_set(spent) if isinstance(spent, dict) else parse_money(spent),
        state=str(node.get("state") or ""),
    )


def parse_location(node: dict[str, Any]) -> LocationRecord:
    return LocationRecord(
        shopify_gid=str(node.get("id") or ""),
        name=str(node.get("name") or ""),
        active=bool(node.get("isActive", True)),
    )


def parse_inventory_levels(variant_node: dict[str, Any]) -> list[InventoryRecord]:
    variant_gid = str(variant_node.get("id") or "")
    item = variant_node.get("inventoryItem")
    item_dict = item if isinstance(item, dict) else {}
    item_gid = item_dict.get("id") if isinstance(item_dict.get("id"), str) else None
    records: list[InventoryRecord] = []
    for level in _edges(item_dict.get("inventoryLevels")):
        location = level.get("location")
        location_gid = ""
        if isinstance(location, dict) and isinstance(location.get("id"), str):
            location_gid = str(location["id"])
        available = 0
        on_hand = 0
        quantities = level.get("quantities")
        if isinstance(quantities, list):
            for qty in quantities:
                if not isinstance(qty, dict):
                    continue
                name = qty.get("name")
                amount = int(qty.get("quantity") or 0)
                if name == "available":
                    available = amount
                elif name == "on_hand":
                    on_hand = amount
        if variant_gid and location_gid:
            records.append(
                InventoryRecord(
                    variant_gid=variant_gid,
                    inventory_item_gid=item_gid,
                    location_gid=location_gid,
                    available=available,
                    on_hand=on_hand,
                )
            )
    return records


def connection_page(payload: dict[str, Any], key: str, parse_one: object) -> Page[Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    connection = data.get(key) if isinstance(data, dict) else None
    has_next, cursor = page_info(connection)
    items = []
    parser = parse_one
    for node in _edges(connection):
        parsed = parser(node)  # type: ignore[operator]
        if isinstance(parsed, list):
            items.extend(parsed)
        else:
            items.append(parsed)
    return Page(items=tuple(items), has_next=has_next, end_cursor=cursor)
