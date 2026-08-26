from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_domain import TenantContext
from merchantos_mcp import (
    FORBIDDEN_TOOL_NAMES,
    READ_TOOLS,
    ToolError,
    ToolErrorCode,
    ToolNotAllowed,
    ToolPermission,
    ToolRegistry,
    UnknownTool,
    build_commerce_registry,
)
from merchantos_mcp.permissions import RiskLevel
from merchantos_mcp.schemas import MAX_LIMIT, DateRangeInput, ProductPerformanceInput
from merchantos_mcp.spec import ToolSpec
from pydantic import BaseModel, ConfigDict, ValidationError


def _ctx() -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("read_orders",),
        )
    )


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = "ok"


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")
    echo: str


def _spec(name: str = "ping", handler=None) -> ToolSpec:
    def _handler(_ctx: TenantContext, args: dict) -> dict[str, object]:
        return {"echo": args.get("q", "ok")}

    return ToolSpec(
        name=name,
        description="ping",
        input_model=_In,
        output_model=_Out,
        permission=ToolPermission.ANALYTICS_READ,
        risk_level=RiskLevel.LOW,
        tenant_required=True,
        timeout_seconds=1.0,
        read_only=True,
        handler=handler or _handler,
    )


def test_registered_tool_is_discoverable() -> None:
    registry = ToolRegistry((_spec(),))
    names = {tool.name for tool in registry.list_tools()}
    assert "ping" in names
    meta = registry.get("ping").metadata()
    assert meta["permission"] == "analytics:read"
    assert meta["risk_level"] == "LOW"
    assert meta["read_only"] is True
    assert meta["tenant_required"] is True
    assert "input_schema" in meta
    assert "output_schema" in meta


def test_unregistered_and_forbidden_tools_cannot_be_called() -> None:
    registry = ToolRegistry((_spec(),))
    ctx = _ctx()
    perms = frozenset({ToolPermission.ANALYTICS_READ})
    with pytest.raises(UnknownTool):
        registry.invoke("nope", {}, ctx, permissions=perms)
    for name in FORBIDDEN_TOOL_NAMES:
        with pytest.raises(UnknownTool):
            registry.invoke(name, {}, ctx, permissions=perms)
        with pytest.raises(ValueError, match="forbidden"):
            registry.register(_spec(name=name))


def test_permission_check_and_invalid_input() -> None:
    registry = ToolRegistry((_spec(),))
    ctx = _ctx()
    with pytest.raises(ToolError) as missing:
        registry.invoke("ping", {}, ctx, permissions=frozenset())
    assert missing.value.code == ToolErrorCode.UNAUTHORIZED
    with pytest.raises(ToolError) as bad:
        registry.invoke(
            "ping",
            {"unexpected": True},
            ctx,
            permissions=frozenset({ToolPermission.ANALYTICS_READ}),
        )
    assert bad.value.code == ToolErrorCode.INVALID_INPUT


def test_tenant_fields_are_stripped_and_context_is_required() -> None:
    seen: dict[str, object] = {}

    def handler(ctx: TenantContext, args: dict) -> dict[str, object]:
        seen["merchant"] = str(ctx.merchant_id)
        seen["args"] = args
        return {"echo": "ok"}

    registry = ToolRegistry((_spec(handler=handler),))
    ctx = _ctx()
    out = registry.invoke(
        "ping",
        {
            "q": "ok",
            "tenant_id": str(uuid4()),
            "merchant_id": str(uuid4()),
            "store_id": str(uuid4()),
        },
        ctx,
        permissions=frozenset({ToolPermission.ANALYTICS_READ}),
    )
    assert out["echo"] == "ok"
    assert "tenant_id" not in seen["args"]
    assert "merchant_id" not in seen["args"]
    assert "store_id" not in seen["args"]
    assert seen["merchant"] == str(ctx.merchant_id)
    with pytest.raises(ToolError) as err:
        registry.invoke(
            "ping",
            {},
            object(),  # type: ignore[arg-type]
            permissions=frozenset({ToolPermission.ANALYTICS_READ}),
        )
    assert err.value.code == ToolErrorCode.UNAUTHORIZED


def test_agent_allowlist_blocks_other_tools() -> None:
    local = ToolRegistry((_spec(), _spec(name="other")))
    port = local.for_agent("orchestrator")
    with pytest.raises(ToolNotAllowed):
        port.invoke("ping", {}, _ctx())
    with pytest.raises(ToolError) as err:
        local.for_agent("strategy")
    assert err.value.code == ToolErrorCode.FORBIDDEN


def test_commerce_catalog_is_read_only_and_complete() -> None:
    class _Fake:
        pass

    registry = build_commerce_registry(_Fake())  # type: ignore[arg-type]
    names = {tool.name for tool in registry.list_tools()}
    assert names == set(READ_TOOLS)
    for spec in registry.list_tools():
        assert spec.read_only is True
        assert spec.risk_level is RiskLevel.LOW
        assert spec.tenant_required is True
        properties = spec.input_model.model_json_schema().get("properties", {})
        assert "tenant_id" not in properties
        assert "merchant_id" not in properties
        assert "store_id" not in properties


def test_input_limits_and_date_range() -> None:
    with pytest.raises(ValidationError):
        ProductPerformanceInput.model_validate({"limit": MAX_LIMIT + 1})
    ProductPerformanceInput.model_validate({"limit": MAX_LIMIT})
    with pytest.raises(ValidationError):
        DateRangeInput.model_validate(
            {"preset": "custom", "from": "2026-08-20", "to": "2026-08-01"}
        )
    with pytest.raises(ValidationError):
        DateRangeInput.model_validate({"preset": "custom"})


def test_timeout_is_typed() -> None:
    def hang(_ctx: TenantContext, _args: dict) -> dict[str, object]:
        import time

        time.sleep(2)
        return {"echo": "late"}

    slow = ToolSpec(
        name="slow",
        description="slow",
        input_model=_In,
        output_model=_Out,
        permission=ToolPermission.ANALYTICS_READ,
        risk_level=RiskLevel.LOW,
        tenant_required=True,
        timeout_seconds=0.05,
        read_only=True,
        handler=hang,
    )
    registry = ToolRegistry((slow,))
    with pytest.raises(ToolError) as err:
        registry.invoke("slow", {}, _ctx(), permissions=frozenset({ToolPermission.ANALYTICS_READ}))
    assert err.value.code == ToolErrorCode.TIMEOUT
    assert "Traceback" not in str(err.value)
