from merchantos_agentbench import run_scenario
from merchantos_agentbench.runner import run_suite
from merchantos_agentbench.scenarios import RUNTIME_OVERVIEW


def test_runtime_overview_scenario() -> None:
    result = run_scenario(RUNTIME_OVERVIEW)
    assert result.passed, result.failures
    assert result.tool_names == ("get_store_overview",)
    assert "Overview" in result.answer


def test_phase7_suite_passes() -> None:
    results = run_suite()
    failed = [item for item in results if not item.passed]
    assert not failed, [(item.scenario_id, item.failures) for item in failed]
    assert {item.scenario_id for item in results} >= {
        "runtime-overview",
        "analytics-revenue",
        "inventory-stockout",
        "customer-mix",
        "analytics-missing",
        "inventory-injection",
        "customer-tenant-switch",
        "customer-unsupported-ltv",
        "intel-revenue-decline",
        "intel-inventory-concern",
        "intel-customer-change",
        "intel-broad-health",
        "intel-conflicting-evidence",
        "intel-insufficient",
        "intel-prompt-injection",
        "intel-cross-tenant",
        "intel-unsupported-causal",
    }
