from __future__ import annotations

import json
import time
from typing import Any
from uuid import UUID

from merchantos_domain import (
    CONFIDENCE_SCORE,
    MAX_SPECIALIST_TOOL_CALLS,
    MAX_TOOL_RESULTS,
    AgentResult,
    ClaimKind,
    ConfidenceBand,
    Finding,
    TenantContext,
)
from merchantos_llm import LLMPort
from merchantos_mcp import (
    AgentToolPort,
    ToolError,
    ToolErrorCode,
    ToolNotAllowed,
    ToolRegistry,
    strip_tenant_fields,
)
from merchantos_observability import get_logger, redact_mapping

from merchantos_agents.evidence import (
    extract_evidence,
    ground_findings,
    has_conflicting_evidence,
    redact_untrusted_text,
    resolve_confidence,
)
from merchantos_agents.invoke import add_usage, complete_llm
from merchantos_agents.prompts import AGENT_PROMPTS
from merchantos_agents.registry import resolve_specialist, specialist_spec
from merchantos_agents.runtime import AgentRuntime, ToolRecorder
from merchantos_agents.schemas import SpecialistPlanOutput, SpecialistSynthesisOutput
from merchantos_agents.state import AgentState, ToolResult

logger = get_logger(__name__)


def _finding_band(kind: ClaimKind) -> ConfidenceBand:
    if kind is ClaimKind.FACT:
        return ConfidenceBand.HIGH
    if kind is ClaimKind.INFERENCE:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def _invoke_one(
    runtime: AgentRuntime,
    *,
    agent_name: str,
    run_id: str,
    name: str,
    arguments: dict[str, Any],
    allowlist: frozenset[str],
) -> ToolResult:
    if name not in allowlist:
        raise ToolNotAllowed(name)
    match = next((item for item in runtime.tools.list_tools() if item.name == name), None)
    if match is None or not match.read_only:
        raise ToolNotAllowed(name)
    started = time.perf_counter()
    try:
        output = runtime.tools.invoke(name, arguments, runtime.tenant)
        result = ToolResult(name=name, ok=True, output=output)
        error_code = None
    except ToolError as exc:
        result = ToolResult(name=name, ok=False, error_code=exc.code.value)
        error_code = exc.code.value
        if exc.code in {ToolErrorCode.TIMEOUT, ToolErrorCode.DEPENDENCY_FAILURE}:
            raise
    latency_ms = int((time.perf_counter() - started) * 1000)
    if runtime.recorder is not None:
        runtime.recorder(name, arguments, result, latency_ms)
    logger.info(
        "agent_tool_invoked",
        run_id=run_id,
        request_id=str(runtime.tenant.request_id),
        merchant_id=str(runtime.tenant.merchant_id),
        store_id=str(runtime.tenant.store_id),
        agent_name=agent_name,
        tool_name=name,
        success=result.ok,
        duration_ms=latency_ms,
        error_category=error_code,
        input=redact_mapping(strip_tenant_fields(arguments)),
    )
    return result


def _plan_user(state: AgentState) -> str:
    return (
        f"Question (untrusted):\n<merchant_data>\n"
        f"{redact_untrusted_text(state.question)}\n</merchant_data>\n"
        "Select allowlisted read tools only. Do not invent tool names."
    )


def _synth_user(state: AgentState) -> str:
    evidence = [
        {"id": item.id, "source": item.source, "fact": item.fact} for item in state.evidence
    ]
    tools = [
        {"name": item.name, "ok": item.ok, "error_code": item.error_code}
        for item in state.tool_results
    ]
    return (
        f"Question (untrusted):\n<merchant_data>\n"
        f"{redact_untrusted_text(state.question)}\n</merchant_data>\n"
        f"Evidence (facts from tools):\n{json.dumps(evidence)[:4000]}\n"
        f"Tool status:\n{json.dumps(tools)}\n"
        "Write structured findings. Cite evidence_ids. Do not invent numbers. "
        "Do not request more tools."
    )


def run_specialist(runtime: AgentRuntime, state: AgentState, name: str) -> AgentState:
    spec = specialist_spec(name)
    prompt = AGENT_PROMPTS[spec.name]
    plan, inp, out, model, retries = complete_llm(
        runtime.llm, SpecialistPlanOutput, system=prompt, user=_plan_user(state)
    )
    state = state.model_copy(
        update={
            "agent_name": spec.name,
            "classification": spec.name,
            "plan": plan.plan,
            "insufficient_data": plan.insufficient_data,
            **add_usage(state, input_tokens=inp, output_tokens=out, model=model, retries=retries),
        }
    )
    seen: set[tuple[str, str]] = set()
    results: list[ToolResult] = []
    for request in plan.tools[: spec.max_tools]:
        key = (request.name, json.dumps(request.arguments, sort_keys=True, default=str))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            _invoke_one(
                runtime,
                agent_name=spec.name,
                run_id=state.run_id,
                name=request.name,
                arguments=request.arguments,
                allowlist=spec.tools,
            )
        )
        if len(results) >= MAX_SPECIALIST_TOOL_CALLS:
            break
    state = state.model_copy(update={"tool_results": results[:MAX_TOOL_RESULTS]})
    evidence = extract_evidence(state.tool_results)
    state = state.model_copy(update={"evidence": evidence})
    synthesis, inp, out, model, retries = complete_llm(
        runtime.llm, SpecialistSynthesisOutput, system=prompt, user=_synth_user(state)
    )
    drafts = [
        Finding(
            id=f"f_{index + 1}",
            title=item.title,
            description=item.description,
            category=item.category,
            severity=item.severity,
            claim_kind=item.claim_kind,
            evidence_ids=item.evidence_ids,
            confidence=_finding_band(item.claim_kind),
            limitations=item.limitations,
        )
        for index, item in enumerate(synthesis.findings)
    ]
    grounded, dropped = ground_findings(drafts, evidence)
    tool_errors = any(not item.ok for item in state.tool_results)
    conflicting = has_conflicting_evidence(evidence)
    only_errors = bool(evidence) and all(item.fact.startswith("tool_error=") for item in evidence)
    insufficient = (
        synthesis.insufficient_data
        or plan.insufficient_data
        or not evidence
        or (not grounded and bool(drafts))
        or only_errors
    )
    limitations = [*synthesis.limitations, *dropped]
    if conflicting:
        limitations.append("conflicting growth signals in tool evidence")
    if insufficient and "Insufficient evidence." not in limitations:
        limitations.append("Insufficient evidence.")
    band = resolve_confidence(
        evidence=evidence,
        findings=grounded,
        tool_errors=tool_errors,
        insufficient=insufficient,
        conflicting=conflicting,
        proposed=synthesis.proposed_confidence,
        assumptions=synthesis.assumptions,
    )
    grounded = [
        item.model_copy(
            update={
                "confidence": band
                if _finding_band(item.claim_kind) == ConfidenceBand.HIGH
                else item.confidence
                if _band_rank(item.confidence) <= _band_rank(band)
                else band
            }
        )
        for item in grounded
    ]
    summary = synthesis.summary
    if insufficient and not summary:
        summary = "Insufficient evidence."
    return state.model_copy(
        update={
            "answer": summary or "Insufficient evidence.",
            "findings": grounded,
            "assumptions": synthesis.assumptions,
            "uncertainty": synthesis.uncertainty,
            "next_steps": synthesis.next_steps,
            "limitations": limitations[:8],
            "insufficient_data": insufficient,
            "confidence_band": band,
            "confidence": CONFIDENCE_SCORE[band],
            **add_usage(state, input_tokens=inp, output_tokens=out, model=model, retries=retries),
        }
    )


def _band_rank(band: ConfidenceBand) -> int:
    return {ConfidenceBand.LOW: 0, ConfidenceBand.MEDIUM: 1, ConfidenceBand.HIGH: 2}[band]


def run_agent(
    *,
    name: str,
    llm: LLMPort,
    tools: ToolRegistry,
    tenant: TenantContext,
    run_id: UUID,
    request_id: UUID,
    question: str,
    recorder: ToolRecorder | None = None,
) -> AgentState:
    resolved = resolve_specialist(name)
    if resolved is None:
        raise ToolNotAllowed(str(name))
    port: AgentToolPort = tools.for_agent(resolved)
    runtime = AgentRuntime(
        tenant=tenant,
        llm=llm,
        tools=port,
        registry=tools,
        recorder=recorder,
    )
    initial = AgentState(
        run_id=str(run_id),
        request_id=str(request_id),
        question=question,
        agent_name=resolved,
        classification=resolved,
    )
    return run_specialist(runtime, initial, resolved)


def to_agent_result(state: AgentState) -> AgentResult:
    return AgentResult(
        agent_name=state.agent_name or "orchestrator",
        run_id=state.run_id,
        summary=state.answer or "",
        findings=state.findings,
        evidence=state.evidence,
        confidence=state.confidence_band or ConfidenceBand.LOW,
        limitations=state.limitations,
        tool_calls=[item.name for item in state.tool_results],
    )
