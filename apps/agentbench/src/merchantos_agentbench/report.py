from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from merchantos_agentbench.runner import ScenarioResult

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPORT_PATH = ROOT / "artifacts" / "eval" / "latest.json"
BASELINE_PATH = ROOT / "artifacts" / "eval" / "baseline.json"


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _rate(passed: int, total: int) -> float:
    if total == 0:
        return 1.0
    return round(passed / total, 4)


@dataclass(frozen=True)
class SuiteReport:
    generated_at: str
    git_sha: str
    model: str
    scenario_count: int
    passed: int
    failed: int
    task_success_rate: float
    agent_selection_accuracy: float
    tool_selection_accuracy: float
    tool_argument_validity: float
    evidence_grounding_rate: float
    structured_output_validity: float
    hallucination_rate: float
    contradiction_handling_rate: float
    prompt_injection_pass_rate: float
    tenant_isolation_failures: int
    unauthorized_mutation_attempts: int
    recommendation_safety_rate: float
    action_policy_compliance_rate: float
    latency_ms_total: int
    latency_ms_p50: int
    latency_ms_max: int
    tool_call_count: int
    llm_call_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: str
    suites: dict[str, dict[str, int]]
    failures: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def build_report(results: list[ScenarioResult]) -> SuiteReport:
    def scored(flag: str) -> list[ScenarioResult]:
        return [item for item in results if flag in item.scored]

    agent = scored("agent_selection")
    tools = scored("tool_selection")
    args = scored("tool_arguments")
    ground = scored("grounding")
    structure = scored("structured_output")
    claims = scored("unsupported_claims")
    contradiction = scored("contradiction")
    injection = [item for item in results if item.suite == "prompt_injection"]
    tenant = scored("tenant_isolation")
    mutation = scored("mutation_safety")
    recommend = scored("recommendation_safety")
    policy = scored("action_policy")
    latencies = [item.latency_ms for item in results]
    return SuiteReport(
        generated_at=datetime.now(UTC).isoformat(),
        git_sha=_git_sha(),
        model="fake",
        scenario_count=len(results),
        passed=sum(1 for item in results if item.passed),
        failed=sum(1 for item in results if not item.passed),
        task_success_rate=_rate(sum(1 for item in results if item.passed), len(results)),
        agent_selection_accuracy=_rate(sum(1 for item in agent if item.passed), len(agent)),
        tool_selection_accuracy=_rate(sum(1 for item in tools if item.passed), len(tools)),
        tool_argument_validity=_rate(sum(1 for item in args if item.passed), len(args)),
        evidence_grounding_rate=_rate(sum(1 for item in ground if item.passed), len(ground)),
        structured_output_validity=_rate(
            sum(1 for item in structure if item.passed), len(structure)
        ),
        hallucination_rate=_rate(
            sum(1 for item in claims if not item.passed),
            len(claims),
        ),
        contradiction_handling_rate=_rate(
            sum(1 for item in contradiction if item.passed),
            len(contradiction),
        ),
        prompt_injection_pass_rate=_rate(
            sum(1 for item in injection if item.passed),
            len(injection),
        ),
        tenant_isolation_failures=sum(1 for item in tenant if not item.passed),
        unauthorized_mutation_attempts=sum(1 for item in mutation if not item.passed),
        recommendation_safety_rate=_rate(
            sum(1 for item in recommend if item.passed),
            len(recommend),
        ),
        action_policy_compliance_rate=_rate(sum(1 for item in policy if item.passed), len(policy)),
        latency_ms_total=sum(latencies),
        latency_ms_p50=_percentile(latencies, 0.5),
        latency_ms_max=max(latencies, default=0),
        tool_call_count=sum(item.tool_calls for item in results),
        llm_call_count=sum(item.llm_calls for item in results),
        input_tokens=sum(item.input_tokens for item in results),
        output_tokens=sum(item.output_tokens for item in results),
        estimated_cost_usd="0",
        suites={
            suite: {
                "count": len(group),
                "passed": sum(1 for item in group if item.passed),
            }
            for suite in sorted({item.suite for item in results})
            for group in ([item for item in results if item.suite == suite],)
        },
        failures=[
            {
                "id": item.scenario_id,
                "suite": item.suite,
                "failures": list(item.failures),
            }
            for item in results
            if not item.passed
        ],
        scenarios=[item.to_dict() for item in results],
    )


def write_report(results: list[ScenarioResult], path: Path | None = None) -> Path:
    target = path or DEFAULT_REPORT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(results)
    target.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    return target
