from pathlib import Path

from merchantos_agents.graph import compile_orchestrator
from merchantos_agents.intelligence import compile_intelligence
from merchantos_agents.invoke import LLM_OUTPUT_RETRIES, LLM_TIMEOUT
from merchantos_domain import MAX_INTEL_AGENTS, MAX_SPECIALIST_TOOL_CALLS

SRC = Path(__file__).resolve().parents[1] / "src" / "merchantos_agents"


def test_graphs_are_dags_and_do_not_reenter() -> None:
    graph_src = (SRC / "graph.py").read_text()
    intel_src = (SRC / "intelligence.py").read_text()
    assert 'graph.add_edge("finalize", END)' in graph_src
    assert 'graph.add_edge("tools", "finalize")' in graph_src
    assert 'graph.add_edge("orchestrate", "orchestrate")' not in graph_src
    assert 'graph.add_edge("recommend", END)' in intel_src
    assert 'graph.add_edge("recommend", "select")' not in intel_src
    assert compile_orchestrator is not None
    assert compile_intelligence is not None
    assert LLM_TIMEOUT == 8.0
    assert LLM_OUTPUT_RETRIES == 2
    assert MAX_SPECIALIST_TOOL_CALLS == 5
    assert MAX_INTEL_AGENTS == 3
