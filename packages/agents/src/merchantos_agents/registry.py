from dataclasses import dataclass

from merchantos_mcp import AGENT_TOOLS, ToolError, ToolErrorCode

SPECIALIST_NAMES = frozenset({"analytics", "inventory", "customer"})
REGISTERED_AGENTS = frozenset({"orchestrator"}) | SPECIALIST_NAMES


class UnknownAgentError(ToolError):
    def __init__(self, name: str) -> None:
        super().__init__(ToolErrorCode.FORBIDDEN, f"unknown agent: {name}")


@dataclass(frozen=True)
class SpecialistSpec:
    name: str
    tools: frozenset[str]
    max_tools: int


def resolve_specialist(name: str | None) -> str | None:
    """Allowlisted specialist lookup. Model output cannot load arbitrary classes."""
    if name is None or name == "":
        return None
    if name not in SPECIALIST_NAMES:
        raise UnknownAgentError(name)
    return name


def specialist_spec(name: str) -> SpecialistSpec:
    resolved = resolve_specialist(name)
    if resolved is None:
        raise UnknownAgentError(str(name))
    return SpecialistSpec(name=resolved, tools=AGENT_TOOLS[resolved], max_tools=5)
