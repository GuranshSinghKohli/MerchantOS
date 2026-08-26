from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from merchantos_domain import TenantContext
from pydantic import BaseModel

from merchantos_mcp.permissions import RiskLevel, ToolPermission

ToolHandler = Callable[[TenantContext, dict[str, Any]], dict[str, object]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    permission: ToolPermission
    risk_level: RiskLevel
    tenant_required: bool
    timeout_seconds: float
    read_only: bool
    handler: ToolHandler

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission.value,
            "risk_level": self.risk_level.value,
            "tenant_required": self.tenant_required,
            "timeout_seconds": self.timeout_seconds,
            "read_only": self.read_only,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
        }
