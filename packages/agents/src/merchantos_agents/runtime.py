from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from merchantos_domain import TenantContext
from merchantos_llm import LLMPort
from merchantos_mcp import AgentToolPort, ToolRegistry

from merchantos_agents.state import ToolResult

ToolRecorder = Callable[[str, dict[str, Any], ToolResult, int], None]


@dataclass(frozen=True)
class AgentRuntime:
    """Trusted per-run bindings. Not part of AgentState and not model-writable."""

    tenant: TenantContext
    llm: LLMPort
    tools: AgentToolPort
    registry: ToolRegistry | None = None
    recorder: ToolRecorder | None = field(default=None)
