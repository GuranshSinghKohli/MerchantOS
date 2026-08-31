from __future__ import annotations

import json
import time
from typing import Any, Literal, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from merchantos_domain import (
    CONFIDENCE_SCORE,
    MAX_QUESTION_CHARS,
    MAX_TOOL_RESULTS,
    AskResult,
    ConfidenceBand,
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

from merchantos_agents.evidence import redact_untrusted_payload, redact_untrusted_text
from merchantos_agents.invoke import add_usage, complete_llm
from merchantos_agents.prompts import AGENT_PROMPTS
from merchantos_agents.registry import UnknownAgentError, resolve_specialist
from merchantos_agents.runtime import AgentRuntime, ToolRecorder
from merchantos_agents.schemas import ORCHESTRATOR_TOOLS, OrchestratorOutput
from merchantos_agents.specialist import run_specialist
from merchantos_agents.state import AgentState, ToolResult

logger = get_logger(__name__)

GRAPH_TIMEOUT_SECONDS = 40.0


class GraphState(TypedDict, total=False):
    run_id: str
    request_id: str
    question: str
    classification: str | None
    agent_name: str | None
    plan: str | None
    evidence: list[dict[str, str]]
    tool_results: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    answer: str | None
    assumptions: list[str]
    uncertainty: str | None
    confidence: float | None
    confidence_band: str | None
    next_steps: list[str]
    limitations: list[str]
    errors: list[str]
    status: str
    insufficient_data: bool
    llm_retries: int
    token_input: int
    token_output: int
    model: str | None
    _pending_tool: dict[str, Any]
    _specialist: str


def _state_from(raw: dict[str, Any]) -> AgentState:
    cleaned = {key: value for key, value in raw.items() if not key.startswith("_")}
    return AgentState.model_validate(cleaned)


def _apply_output(
    state: AgentState,
    output: OrchestratorOutput,
    *,
    input_tokens: int,
    output_tokens: int,
    model: str,
    retries: int,
) -> AgentState:
    return state.model_copy(
        update={
            "classification": output.classification,
            "plan": output.plan,
            "answer": output.answer or state.answer,
            "assumptions": output.assumptions,
            "uncertainty": output.uncertainty,
            "confidence": output.confidence,
            "next_steps": output.next_steps,
            "evidence": output.evidence,
            "insufficient_data": output.insufficient_data
            or output.classification == "insufficient_data",
            **add_usage(
                state,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                retries=retries,
            ),
        }
    )


def _orchestrate(runtime: AgentRuntime, raw: dict[str, Any]) -> dict[str, Any]:
    state = _state_from(raw)
    data, inp, out, model, retries = complete_llm(
        runtime.llm,
        OrchestratorOutput,
        system=AGENT_PROMPTS["orchestrator"],
        user=(
            f"Question (untrusted):\n<merchant_data>\n"
            f"{redact_untrusted_text(state.question[:MAX_QUESTION_CHARS])}\n"
            "</merchant_data>"
        ),
    )
    updated = _apply_output(
        state, data, input_tokens=inp, output_tokens=out, model=model, retries=retries
    )
    payload = updated.as_graph()
    specialist = None
    if data.specialist is not None:
        try:
            specialist = resolve_specialist(data.specialist)
        except UnknownAgentError:
            specialist = None
            payload["limitations"] = ["unknown specialist ignored"]
    if specialist is not None and runtime.registry is not None:
        payload["agent_name"] = specialist
        payload["classification"] = specialist
        payload["_specialist"] = specialist
        return payload
    if data.tool is not None:
        payload["_pending_tool"] = data.tool.model_dump()
    return payload


def _run_specialist_node(runtime: AgentRuntime, raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("_specialist") or "")
    resolved = resolve_specialist(name)
    if resolved is None or runtime.registry is None:
        return _state_from(raw).as_graph()
    bound = AgentRuntime(
        tenant=runtime.tenant,
        llm=runtime.llm,
        tools=runtime.registry.for_agent(resolved),
        registry=runtime.registry,
        recorder=runtime.recorder,
    )
    return run_specialist(bound, _state_from(raw), resolved).as_graph()


def _invoke_tool(runtime: AgentRuntime, raw: dict[str, Any]) -> dict[str, Any]:
    pending = raw.get("_pending_tool")
    state = _state_from(raw)
    if not isinstance(pending, dict):
        return state.as_graph()
    name = str(pending.get("name", ""))
    raw_args = pending.get("arguments")
    arguments: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
    if name not in ORCHESTRATOR_TOOLS:
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
        run_id=state.run_id,
        request_id=state.request_id,
        merchant_id=str(runtime.tenant.merchant_id),
        store_id=str(runtime.tenant.store_id),
        agent_name="orchestrator",
        tool_name=name,
        success=result.ok,
        duration_ms=latency_ms,
        error_category=error_code,
        input=redact_mapping(strip_tenant_fields(arguments)),
    )
    results = [*state.tool_results, result]
    return state.model_copy(update={"tool_results": results[:MAX_TOOL_RESULTS]}).as_graph()


def _finalize(runtime: AgentRuntime, raw: dict[str, Any]) -> dict[str, Any]:
    state = _state_from(raw)
    if state.agent_name in {"analytics", "inventory", "customer"} and state.answer:
        return state.as_graph()
    if state.tool_results:
        payload = json.dumps(
            redact_untrusted_payload(
                [
                    {"name": item.name, "ok": item.ok, "output": item.output}
                    for item in state.tool_results
                ]
            )
        )[:4000]
        data, inp, out, model, retries = complete_llm(
            runtime.llm,
            OrchestratorOutput,
            system=AGENT_PROMPTS["orchestrator"],
            user=(
                f"Question (untrusted):\n<merchant_data>\n"
                f"{redact_untrusted_text(state.question[:MAX_QUESTION_CHARS])}\n"
                f"</merchant_data>\nTool results (facts):\n{payload}\n"
                "Write the merchant answer. Do not invent numbers. Do not request another tool."
            ),
        )
        if data.tool is not None:
            data = data.model_copy(update={"tool": None})
        state = _apply_output(
            state, data, input_tokens=inp, output_tokens=out, model=model, retries=retries
        )
    if not state.answer:
        state = state.model_copy(
            update={
                "answer": "I do not have enough store evidence to answer yet.",
                "insufficient_data": True,
                "confidence_band": ConfidenceBand.LOW,
                "confidence": CONFIDENCE_SCORE[ConfidenceBand.LOW],
            }
        )
    return state.as_graph()


def _route(raw: dict[str, Any]) -> Literal["specialist", "tools", "finalize"]:
    if raw.get("_specialist"):
        return "specialist"
    if raw.get("_pending_tool"):
        return "tools"
    return "finalize"


def compile_orchestrator(runtime: AgentRuntime) -> Any:
    graph = StateGraph(GraphState)

    def orchestrate(raw: GraphState) -> GraphState:
        return _orchestrate(runtime, dict(raw))  # type: ignore[return-value]

    def specialist(raw: GraphState) -> GraphState:
        return _run_specialist_node(runtime, dict(raw))  # type: ignore[return-value]

    def tools(raw: GraphState) -> GraphState:
        return _invoke_tool(runtime, dict(raw))  # type: ignore[return-value]

    def finalize(raw: GraphState) -> GraphState:
        return _finalize(runtime, dict(raw))  # type: ignore[return-value]

    graph.add_node("orchestrate", orchestrate)  # type: ignore[call-overload]
    graph.add_node("specialist", specialist)  # type: ignore[call-overload]
    graph.add_node("tools", tools)  # type: ignore[call-overload]
    graph.add_node("finalize", finalize)  # type: ignore[call-overload]
    graph.add_edge(START, "orchestrate")
    graph.add_conditional_edges(
        "orchestrate",
        _route,
        {"specialist": "specialist", "tools": "tools", "finalize": "finalize"},
    )
    graph.add_edge("specialist", END)
    graph.add_edge("tools", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _bind_tools(
    tools: ToolRegistry | AgentToolPort,
) -> tuple[AgentToolPort, ToolRegistry | None]:
    if isinstance(tools, ToolRegistry):
        return tools.for_agent("orchestrator"), tools
    return tools, None


def run_orchestrator(
    *,
    llm: LLMPort,
    tools: ToolRegistry | AgentToolPort,
    tenant: TenantContext,
    run_id: UUID,
    request_id: UUID,
    question: str,
    recorder: ToolRecorder | None = None,
) -> AgentState:
    port, registry = _bind_tools(tools)
    runtime = AgentRuntime(tenant=tenant, llm=llm, tools=port, registry=registry, recorder=recorder)
    compiled = compile_orchestrator(runtime)
    initial = AgentState(run_id=str(run_id), request_id=str(request_id), question=question)
    raw = compiled.invoke(initial.as_graph())
    return _state_from(dict(raw))


def to_ask_result(state: AgentState) -> AskResult:
    return AskResult(
        answer=state.answer or "",
        evidence=state.evidence,
        assumptions=state.assumptions,
        uncertainty=state.uncertainty or "",
        confidence=state.confidence or 0.0,
        next_steps=state.next_steps,
        insufficient_data=state.insufficient_data,
        agent_name=state.agent_name,
        findings=state.findings,
        limitations=state.limitations,
        confidence_band=state.confidence_band,
    )
