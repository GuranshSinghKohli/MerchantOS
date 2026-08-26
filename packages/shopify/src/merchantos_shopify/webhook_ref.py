from __future__ import annotations

import json


def extract_webhook_ref(topic: str, body: bytes) -> tuple[str | None, str]:
    """Cheap identifier extract. Stores GIDs only — not customer PII."""
    try:
        data = json.loads(body.decode() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "{}"
    if not isinstance(data, dict):
        return None, "{}"
    gid = data.get("admin_graphql_api_id")
    if isinstance(gid, str) and gid.startswith("gid://"):
        return gid, json.dumps({"admin_graphql_api_id": gid}, separators=(",", ":"))
    if topic.startswith("inventory_levels"):
        item = data.get("inventory_item_id")
        loc = data.get("location_id")
        available = data.get("available")
        item_gid = f"gid://shopify/InventoryItem/{item}" if item is not None else None
        loc_gid = f"gid://shopify/Location/{loc}" if loc is not None else None
        payload = {
            "inventory_item_gid": item_gid,
            "location_gid": loc_gid,
            "available": available if isinstance(available, int) else None,
        }
        return item_gid, json.dumps(payload, separators=(",", ":"))
    numeric_id = data.get("id")
    mapping = (
        ("products/", "Product"),
        ("orders/", "Order"),
        ("customers/", "Customer"),
        ("locations/", "Location"),
    )
    for prefix, typename in mapping:
        if topic.startswith(prefix.rstrip("/")):
            if numeric_id is not None:
                built = f"gid://shopify/{typename}/{numeric_id}"
                return built, json.dumps({"admin_graphql_api_id": built}, separators=(",", ":"))
    return None, "{}"
