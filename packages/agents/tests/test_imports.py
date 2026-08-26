import merchantos_agents
import merchantos_agents.graph
import merchantos_agents.state


def test_agents_package_does_not_export_approval_or_mutator() -> None:
    assert not hasattr(merchantos_agents, "ApprovedAction")
    assert "ApprovedAction" not in dir(merchantos_agents)
    assert "ShopifyMutator" not in dir(merchantos_agents)
