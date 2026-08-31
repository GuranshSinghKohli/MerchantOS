from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "apps/worker/src/merchantos_worker/handlers/agent.py"
EXEC = ROOT / "apps/worker/src/merchantos_worker/handlers/execution.py"
MCP = ROOT / "packages/mcp/src/merchantos_mcp/registry.py"
GRAPH = ROOT / "packages/agents/src/merchantos_agents/graph.py"


def test_correlation_ids_are_logged_across_the_path() -> None:
    agent = AGENT.read_text()
    execution = EXEC.read_text()
    mcp = MCP.read_text()
    graph = GRAPH.read_text()
    for source in (agent, mcp, graph, execution):
        assert "request_id" in source or "job_id" in source
        assert "merchant_id" in source or "action_id" in source
    assert "run_id" in agent
    assert "run_id" in graph
    assert "request_id" in mcp
    assert "action_id" in execution
    assert "redact_mapping" in agent
    assert "redact_mapping" in mcp


def test_cloudwatch_query_doc_exists() -> None:
    deploy = (ROOT / "docs/deployment.md").read_text()
    assert "fields @timestamp" in deploy or "CloudWatch" in deploy
    assert "request_id" in deploy
