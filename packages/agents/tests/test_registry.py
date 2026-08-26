import pytest
from merchantos_agents import REGISTERED_AGENTS, SPECIALIST_NAMES, resolve_specialist
from merchantos_agents.registry import UnknownAgentError, specialist_spec
from merchantos_mcp import AGENT_TOOLS


def test_specialists_are_explicitly_registered() -> None:
    assert SPECIALIST_NAMES == frozenset({"analytics", "inventory", "customer"})
    assert SPECIALIST_NAMES <= REGISTERED_AGENTS
    assert "strategy" not in REGISTERED_AGENTS
    assert "action_planner" not in REGISTERED_AGENTS


@pytest.mark.parametrize("name", sorted(SPECIALIST_NAMES))
def test_allowlists_match_mcp(name: str) -> None:
    spec = specialist_spec(name)
    assert spec.tools == AGENT_TOOLS[name]
    assert spec.tools
    assert spec.max_tools == 5


def test_unknown_agent_cannot_be_loaded() -> None:
    for name in ("strategy", "__import__", "os.system", "AnalyticsAgent"):
        with pytest.raises(UnknownAgentError):
            resolve_specialist(name)
    assert resolve_specialist(None) is None
