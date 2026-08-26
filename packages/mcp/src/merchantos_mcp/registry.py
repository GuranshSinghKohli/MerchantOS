from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any
from uuid import uuid4

from merchantos_domain import (
    DomainError,
    InvalidDateRangeError,
    TenantContext,
    UnauthorizedError,
)
from merchantos_observability import get_logger, redact_mapping
from pydantic import ValidationError

from merchantos_mcp.allowlists import AGENT_TOOLS, FORBIDDEN_TOOL_NAMES
from merchantos_mcp.errors import (
    ToolError,
    ToolErrorCode,
    ToolNotAllowed,
    UnknownTool,
)
from merchantos_mcp.permissions import ToolPermission
from merchantos_mcp.spec import ToolSpec

_TENANT_KEYS = frozenset(
    {
        "tenant_id",
        "merchant_id",
        "store_id",
        "tenantId",
        "merchantId",
        "storeId",
    }
)

logger = get_logger(__name__)


def strip_tenant_fields(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if key not in _TENANT_KEYS}


class ToolRegistry:
    """Explicit allowlisted registry. Unregistered names cannot be invoked."""

    def __init__(self, tools: tuple[ToolSpec, ...]) -> None:
        names = [tool.name for tool in tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tool registration")
        forbidden = set(names) & FORBIDDEN_TOOL_NAMES
        if forbidden:
            raise ValueError(f"forbidden tools cannot be registered: {sorted(forbidden)}")
        self._tools = {tool.name: tool for tool in tools}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in FORBIDDEN_TOOL_NAMES:
            raise ValueError(f"forbidden tool: {spec.name}")
        if spec.name in self._tools:
            raise ValueError(f"already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name in FORBIDDEN_TOOL_NAMES or name not in self._tools:
            raise UnknownTool(name)
        return self._tools[name]

    def list_tools(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

    def for_agent(self, agent_name: str) -> AgentToolPort:
        allowlist = AGENT_TOOLS.get(agent_name)
        if allowlist is None:
            raise ToolError(ToolErrorCode.FORBIDDEN, f"unknown agent: {agent_name}")
        return AgentToolPort(self, allowlist)

    def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: TenantContext,
        *,
        permissions: frozenset[ToolPermission],
    ) -> dict[str, object]:
        if not isinstance(ctx, TenantContext):
            raise ToolError(ToolErrorCode.UNAUTHORIZED, "trusted tenant context is required")
        spec = self.get(name)
        if spec.permission not in permissions:
            raise ToolError(ToolErrorCode.UNAUTHORIZED, "missing tool permission")
        cleaned = strip_tenant_fields(arguments)
        try:
            parsed = spec.input_model.model_validate(cleaned)
        except ValidationError as exc:
            raise ToolError(ToolErrorCode.INVALID_INPUT, "invalid tool input") from exc
        started = time.perf_counter()
        call_id = str(uuid4())
        success = False
        error_category: str | None = None
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(spec.handler, ctx, parsed.model_dump())
                raw = future.result(timeout=spec.timeout_seconds)
            output = spec.output_model.model_validate(raw).model_dump(mode="json")
            success = True
            return output
        except FuturesTimeout as exc:
            error_category = ToolErrorCode.TIMEOUT.value
            raise ToolError(ToolErrorCode.TIMEOUT, "tool timed out") from exc
        except ToolError as exc:
            error_category = exc.code.value
            raise
        except InvalidDateRangeError as exc:
            error_category = ToolErrorCode.INVALID_INPUT.value
            raise ToolError(ToolErrorCode.INVALID_INPUT, str(exc)) from exc
        except UnauthorizedError as exc:
            error_category = ToolErrorCode.UNAUTHORIZED.value
            raise ToolError(ToolErrorCode.UNAUTHORIZED, "not authorized") from exc
        except DomainError as exc:
            error_category = ToolErrorCode.DEPENDENCY_FAILURE.value
            raise ToolError(ToolErrorCode.DEPENDENCY_FAILURE, "dependency failed") from exc
        except ValidationError as exc:
            error_category = ToolErrorCode.INTERNAL_FAILURE.value
            raise ToolError(ToolErrorCode.INTERNAL_FAILURE, "tool output failed schema") from exc
        except Exception as exc:
            error_category = ToolErrorCode.INTERNAL_FAILURE.value
            raise ToolError(ToolErrorCode.INTERNAL_FAILURE, "tool failed") from exc
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "tool_invoked",
                tool_call_id=call_id,
                tool_name=name,
                request_id=str(ctx.request_id),
                merchant_id=str(ctx.merchant_id),
                store_id=str(ctx.store_id),
                duration_ms=duration_ms,
                success=success,
                error_category=error_category,
                input=redact_mapping(cleaned),
            )


class AgentToolPort:
    """Allowlisted proxy. Cannot bind the full registry."""

    def __init__(self, registry: ToolRegistry, allowlist: frozenset[str]) -> None:
        self._registry = registry
        self._allowlist = allowlist
        registered = {spec.name for spec in registry.list_tools()}
        self._permissions = frozenset(
            registry.get(name).permission for name in allowlist if name in registered
        )

    def invoke(self, name: str, arguments: dict[str, Any], ctx: TenantContext) -> dict[str, object]:
        if name not in self._allowlist:
            raise ToolNotAllowed(name)
        return self._registry.invoke(name, arguments, ctx, permissions=self._permissions)

    def list_tools(self) -> tuple[ToolSpec, ...]:
        return tuple(spec for spec in self._registry.list_tools() if spec.name in self._allowlist)
