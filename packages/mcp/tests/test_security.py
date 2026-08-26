from pathlib import Path
from uuid import uuid4

import pytest
from merchantos_domain import ForbiddenFactoryError, TenantContext, UnauthorizedError
from merchantos_mcp import (
    FORBIDDEN_TOOL_NAMES,
    ToolError,
    ToolErrorCode,
    ToolPermission,
    UnknownTool,
    build_commerce_registry,
)
from merchantos_mcp.registry import strip_tenant_fields

from .fakes import (
    ALL_READ,
    BrokenOutputService,
    FailingAnalyticsService,
    FakeAnalyticsService,
    session_ctx,
)

MCP_SRC = Path(__file__).resolve().parents[1] / "src" / "merchantos_mcp"

FORBIDDEN_IMPORTS = (
    "httpx",
    "requests",
    "subprocess",
    "ShopifyMutator",
    "create_engine",
    "text(",
    "os.system",
    "socket",
)


def test_forbidden_capability_names_are_unknown() -> None:
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    ctx = session_ctx()
    for name in (
        *FORBIDDEN_TOOL_NAMES,
        "SELECT * FROM orders",
        "https://evil.example/steal",
        "/bin/sh",
    ):
        with pytest.raises(UnknownTool):
            registry.invoke(name, {}, ctx, permissions=ALL_READ)


def test_sql_http_and_oversized_inputs_fail_validation() -> None:
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    ctx = session_ctx()
    attacks = (
        {"preset": "last_30; DROP TABLE orders"},
        {"sql": "SELECT 1"},
        {"url": "https://evil.example"},
        {"command": "rm -rf /"},
        {"limit": 10_000},
        {"offset": 50_000},
        {"sort": "revenue; drop table"},
        {"from": "2026-08-20", "to": "2026-08-01", "preset": "custom"},
        {"preset": "custom"},
        {"payload": "x" * 20_000},
        {"merchant_id": str(uuid4()), "sql": "1=1"},
    )
    for args in attacks:
        with pytest.raises(ToolError) as err:
            registry.invoke("get_product_performance", args, ctx, permissions=ALL_READ)
        assert err.value.code == ToolErrorCode.INVALID_INPUT
        assert "Traceback" not in str(err.value)


def test_tenant_args_cannot_switch_identity() -> None:
    cleaned = strip_tenant_fields(
        {
            "preset": "last_30",
            "tenant_id": str(uuid4()),
            "merchant_id": str(uuid4()),
            "store_id": str(uuid4()),
            "tenantId": str(uuid4()),
        }
    )
    assert cleaned == {"preset": "last_30"}
    with pytest.raises(ForbiddenFactoryError):
        TenantContext.model_validate({"merchant_id": uuid4(), "store_id": uuid4()})
    assert not hasattr(TenantContext, "from_tool_args")


def test_missing_and_wrong_permissions() -> None:
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    ctx = session_ctx()
    with pytest.raises(ToolError) as missing:
        registry.invoke("get_inventory_health", {}, ctx, permissions=frozenset())
    assert missing.value.code == ToolErrorCode.UNAUTHORIZED
    with pytest.raises(ToolError) as wrong:
        registry.invoke(
            "get_customer_metrics",
            {},
            ctx,
            permissions=frozenset({ToolPermission.PRODUCTS_READ}),
        )
    assert wrong.value.code == ToolErrorCode.UNAUTHORIZED


def test_service_unauthorized_and_broken_output() -> None:
    ctx = session_ctx()
    failing = build_commerce_registry(FailingAnalyticsService(UnauthorizedError("no")))  # type: ignore[arg-type]
    with pytest.raises(ToolError) as err:
        failing.invoke("get_store_overview", {}, ctx, permissions=ALL_READ)
    assert err.value.code == ToolErrorCode.UNAUTHORIZED
    broken = build_commerce_registry(BrokenOutputService())  # type: ignore[arg-type]
    with pytest.raises(ToolError) as schema:
        broken.invoke("get_store_overview", {}, ctx, permissions=ALL_READ)
    assert schema.value.code == ToolErrorCode.INTERNAL_FAILURE


def test_source_has_no_escape_hatches() -> None:
    for path in MCP_SRC.rglob("*.py"):
        text = path.read_text()
        for needle in FORBIDDEN_IMPORTS:
            assert needle not in text, f"{path} contains {needle}"


def test_telemetry_redacts_and_omits_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class _Log:
        def info(self, event: str, **kwargs: object) -> None:
            events.append((event, kwargs))

    monkeypatch.setattr("merchantos_mcp.registry.logger", _Log())
    registry = build_commerce_registry(FakeAnalyticsService())  # type: ignore[arg-type]
    ctx = session_ctx()
    registry.invoke("get_store_overview", {"preset": "last_7"}, ctx, permissions=ALL_READ)
    assert events
    event, payload = events[0]
    assert event == "tool_invoked"
    assert payload["success"] is True
    assert payload["tool_name"] == "get_store_overview"
    assert payload["merchant_id"] == str(ctx.merchant_id)
    blob = str(payload)
    assert "shpua_" not in blob
    assert "access_token" not in blob
    assert "@" not in blob
