from merchantos_shopify.webhook_ref import extract_webhook_ref


def test_extracts_admin_graphql_id() -> None:
    gid, payload = extract_webhook_ref(
        "products/update",
        b'{"id": 1, "admin_graphql_api_id": "gid://shopify/Product/1", "email": "x@y.com"}',
    )
    assert gid == "gid://shopify/Product/1"
    assert "email" not in payload


def test_inventory_level_ids() -> None:
    gid, payload = extract_webhook_ref(
        "inventory_levels/update",
        b'{"inventory_item_id": 9, "location_id": 3, "available": 4}',
    )
    assert gid == "gid://shopify/InventoryItem/9"
    assert "gid://shopify/Location/3" in payload
