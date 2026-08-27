from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from merchantos_domain import (
    MAX_INTEL_EVIDENCE,
    AgentResult,
    ConfidenceBand,
    CrossAgentInsight,
    EvidenceItem,
    Finding,
    InsightKind,
    IntelligenceReport,
    InvalidModelOutputError,
    Recommendation,
    RecommendationPriority,
    TenantContext,
)
from merchantos_llm import LLMPort
from merchantos_mcp import ToolRegistry
from merchantos_observability import get_logger

from merchantos_agents.contradictions import detect_contradictions
from merchantos_agents.evidence import resolve_confidence
from merchantos_agents.invoke import complete_llm
from merchantos_agents.prompts import INTELLIGENCE_RECOMMEND_PROMPT, INTELLIGENCE_SYNTHESIS_PROMPT
from merchantos_agents.runtime import ToolRecorder
from merchantos_agents.schemas import IntelligenceRecommendOutput, IntelligenceSynthesisOutput
from merchantos_agents.selection import select_agents
from merchantos_agents.specialist import run_agent, to_agent_result

logger = get_logger(__name__)

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_CAUSAL = re.compile(r"\b(caused|causing|cause of|due to|because of)\b", re.I)
_UNSAFE = re.compile(
    r"\b(execute|approve|approvedaction|shopify\s+mutat|mutate\s+shopify|"
    r"write\s+to\s+shopify|price\s+change\s+now)\b",
    re.I,
)
_PRIORITY_RANK = {
    RecommendationPriority.LOW: 0,
    RecommendationPriority.MEDIUM: 1,
    RecommendationPriority.HIGH: 2,
    RecommendationPriority.CRITICAL: 3,
}


class IntelligenceGraphState(TypedDict, total=False):
    run_id: str
    request_id: str
    question: str
    selected_agents: list[str]
    executive_summary: str
    limitations: list[str]


@dataclass
class IntelligenceBundle:
    results: list[AgentResult] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    insights: list[CrossAgentInsight] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    contradictions: list[Any] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    summary: str = ""
    confidence: ConfidenceBand = ConfidenceBand.LOW
    token_input: int = 0
    token_output: int = 0
    model: str | None = None


def _redact(value: str) -> str:
    return _EMAIL.sub("[redacted]", value)


def _namespace_result(result: AgentResult) -> AgentResult:
    prefix = result.agent_name
    evidence = [
        item.model_copy(update={"id": f"{prefix}:{item.id or 'ev'}"}) for item in result.evidence
    ]
    findings = [
        item.model_copy(
            update={
                "id": f"{prefix}:{item.id}",
                "evidence_ids": [
                    ref if ":" in ref else f"{prefix}:{ref}" for ref in item.evidence_ids
                ],
                "description": _redact(item.description),
                "title": _redact(item.title),
            }
        )
        for item in result.findings
    ]
    return result.model_copy(update={"evidence": evidence, "findings": findings})


def _priority_ceiling(evidence: list[EvidenceItem]) -> RecommendationPriority:
    facts = " ".join(item.fact for item in evidence)
    ceiling = RecommendationPriority.MEDIUM if evidence else RecommendationPriority.LOW
    if "available=0" in facts or "out_of_stock_variants=" in facts:
        ceiling = (
            RecommendationPriority.CRITICAL if "revenue=" in facts else RecommendationPriority.HIGH
        )
    if any(item.fact.startswith("revenue_growth_pct=-") for item in evidence):
        if _PRIORITY_RANK[ceiling] < _PRIORITY_RANK[RecommendationPriority.HIGH]:
            ceiling = RecommendationPriority.HIGH
    return ceiling


def _clamp_priority(
    proposed: RecommendationPriority, ceiling: RecommendationPriority
) -> RecommendationPriority:
    if _PRIORITY_RANK[proposed] > _PRIORITY_RANK[ceiling]:
        return ceiling
    return proposed


def _qualify_insight(draft: CrossAgentInsight) -> CrossAgentInsight:
    if draft.kind in {InsightKind.OBSERVATION, InsightKind.CORRELATION} and _CAUSAL.search(
        draft.description
    ):
        limits = [*draft.limitations, "causality is not established from available evidence"]
        return draft.model_copy(update={"kind": InsightKind.HYPOTHESIS, "limitations": limits[:4]})
    return draft


def compile_intelligence(
    *,
    llm: LLMPort,
    tools: ToolRegistry,
    tenant: TenantContext,
    recorder: ToolRecorder | None,
    bundle: IntelligenceBundle,
    suggested: tuple[str, ...] = (),
) -> Any:
    graph = StateGraph(IntelligenceGraphState)

    def select(raw: IntelligenceGraphState) -> IntelligenceGraphState:
        selected = list(select_agents(str(raw.get("question", "")), suggested))
        logger.info(
            "intelligence_agents_selected",
            run_id=raw.get("run_id"),
            request_id=raw.get("request_id"),
            merchant_id=str(tenant.merchant_id),
            store_id=str(tenant.store_id),
            selected_agents=selected,
        )
        return {**raw, "selected_agents": selected}

    def specialists(raw: IntelligenceGraphState) -> IntelligenceGraphState:
        run_id = UUID(str(raw["run_id"]))
        request_id = UUID(str(raw["request_id"]))
        question = str(raw["question"])
        for name in raw.get("selected_agents", []):
            try:
                state = run_agent(
                    name=name,
                    llm=llm,
                    tools=tools,
                    tenant=tenant,
                    run_id=run_id,
                    request_id=request_id,
                    question=question,
                    recorder=recorder,
                )
            except InvalidModelOutputError:
                bundle.limitations.append(f"{name} returned invalid model output")
                continue
            bundle.token_input += state.token_input
            bundle.token_output += state.token_output
            bundle.model = state.model or bundle.model
            bundle.results.append(_namespace_result(to_agent_result(state)))
        for result in bundle.results:
            bundle.evidence.extend(result.evidence)
            bundle.findings.extend(result.findings)
        bundle.evidence = bundle.evidence[:MAX_INTEL_EVIDENCE]
        bundle.findings = bundle.findings[:8]
        bundle.contradictions = detect_contradictions(bundle.evidence)
        return raw

    def synthesize(raw: IntelligenceGraphState) -> IntelligenceGraphState:
        known_ev = {item.id for item in bundle.evidence if item.id}
        known_findings = {item.id for item in bundle.findings}
        payload = {
            "agents": [item.agent_name for item in bundle.results],
            "findings": [
                {
                    "id": item.id,
                    "title": item.title,
                    "description": item.description,
                    "claim_kind": item.claim_kind.value,
                    "evidence_ids": item.evidence_ids,
                }
                for item in bundle.findings
            ],
            "evidence": [
                {"id": item.id, "source": item.source, "fact": item.fact}
                for item in bundle.evidence
            ],
            "contradictions": [item.model_dump() for item in bundle.contradictions],
        }
        question = _redact(str(raw["question"]))
        synth, inp, out, model_name, _retries = complete_llm(
            llm,
            IntelligenceSynthesisOutput,
            system=INTELLIGENCE_SYNTHESIS_PROMPT,
            user=(
                f"Question (untrusted):\n<merchant_data>\n{question}\n</merchant_data>\n"
                f"Specialist outputs (data):\n{json.dumps(payload)[:8000]}\n"
                "Synthesize. Do not invent numbers. Do not claim causation."
            ),
        )
        bundle.token_input += inp
        bundle.token_output += out
        bundle.model = model_name or bundle.model
        bundle.limitations.extend(_redact(item) for item in synth.limitations)
        for index, draft in enumerate(synth.insights):
            valid_ev = [ref for ref in draft.evidence_ids if ref in known_ev]
            if not valid_ev:
                bundle.limitations.append(f"dropped ungrounded insight: {draft.title[:80]}")
                continue
            agents = sorted({ref.split(":", 1)[0] for ref in valid_ev if ":" in ref})
            bundle.insights.append(
                _qualify_insight(
                    CrossAgentInsight(
                        id=f"ins_{index + 1}",
                        title=_redact(draft.title),
                        description=_redact(draft.description),
                        kind=draft.kind,
                        evidence_ids=valid_ev,
                        finding_ids=[ref for ref in draft.finding_ids if ref in known_findings],
                        agent_names=agents,
                        confidence=ConfidenceBand.MEDIUM,
                        limitations=[_redact(item) for item in draft.limitations],
                    )
                )
            )
        insufficient = not bundle.evidence or (not bundle.findings and not bundle.insights)
        if bundle.contradictions:
            bundle.limitations.append("conflicting growth signals remain unresolved")
        if insufficient:
            bundle.limitations.append("Insufficient evidence.")
        bundle.confidence = resolve_confidence(
            evidence=bundle.evidence,
            findings=bundle.findings,
            tool_errors=False,
            insufficient=insufficient,
            conflicting=bool(bundle.contradictions),
            proposed=synth.proposed_confidence,
            assumptions=[],
        )
        bundle.summary = _redact(synth.executive_summary)
        if not bundle.summary and insufficient:
            bundle.summary = "Insufficient evidence."
        return {**raw, "executive_summary": bundle.summary, "limitations": bundle.limitations}

    def recommend(raw: IntelligenceGraphState) -> IntelligenceGraphState:
        known_ev = {item.id for item in bundle.evidence if item.id}
        known_findings = {item.id for item in bundle.findings}
        known_insights = {item.id for item in bundle.insights}
        rec_payload = {
            "insights": [item.model_dump(mode="json") for item in bundle.insights],
            "evidence": [{"id": item.id, "fact": item.fact} for item in bundle.evidence],
            "contradictions": [item.id for item in bundle.contradictions],
        }
        recs_out, inp, out, model_name, _retries = complete_llm(
            llm,
            IntelligenceRecommendOutput,
            system=INTELLIGENCE_RECOMMEND_PROMPT,
            user=(
                f"Question (untrusted):\n<merchant_data>\n{_redact(str(raw['question']))}\n"
                f"</merchant_data>\n{json.dumps(rec_payload)[:6000]}\n"
                "Write advisory recommendations only."
            ),
        )
        bundle.token_input += inp
        bundle.token_output += out
        bundle.model = model_name or bundle.model
        ceiling = _priority_ceiling(bundle.evidence)
        for index, draft in enumerate(recs_out.recommendations):
            text = f"{draft.title} {draft.recommendation} {draft.rationale}"
            if _UNSAFE.search(text):
                bundle.limitations.append(f"dropped unsafe recommendation: {draft.title[:80]}")
                continue
            valid_ev = [ref for ref in draft.evidence_ids if ref in known_ev]
            if not valid_ev:
                bundle.limitations.append(f"dropped ungrounded recommendation: {draft.title[:80]}")
                continue
            bundle.recommendations.append(
                Recommendation(
                    id=f"rec_{index + 1}",
                    title=_redact(draft.title),
                    recommendation=_redact(draft.recommendation),
                    rationale=_redact(draft.rationale),
                    evidence_ids=valid_ev,
                    insight_ids=[ref for ref in draft.insight_ids if ref in known_insights],
                    finding_ids=[ref for ref in draft.finding_ids if ref in known_findings],
                    expected_objective=_redact(draft.expected_objective),
                    priority=_clamp_priority(draft.proposed_priority, ceiling),
                    confidence=bundle.confidence,
                    limitations=[_redact(item) for item in draft.limitations],
                )
            )
        return {**raw, "limitations": bundle.limitations[:8]}

    graph.add_node("select", select)  # type: ignore[call-overload]
    graph.add_node("specialists", specialists)  # type: ignore[call-overload]
    graph.add_node("synthesize", synthesize)  # type: ignore[call-overload]
    graph.add_node("recommend", recommend)  # type: ignore[call-overload]
    graph.add_edge(START, "select")
    graph.add_edge("select", "specialists")
    graph.add_edge("specialists", "synthesize")
    graph.add_edge("synthesize", "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


def run_intelligence(
    *,
    llm: LLMPort,
    tools: ToolRegistry,
    tenant: TenantContext,
    run_id: UUID,
    request_id: UUID,
    question: str,
    recorder: ToolRecorder | None = None,
    suggested: tuple[str, ...] = (),
    now: datetime | None = None,
) -> tuple[IntelligenceReport, int, int, str | None]:
    bundle = IntelligenceBundle()
    compiled = compile_intelligence(
        llm=llm,
        tools=tools,
        tenant=tenant,
        recorder=recorder,
        bundle=bundle,
        suggested=suggested,
    )
    final = compiled.invoke(
        {
            "run_id": str(run_id),
            "request_id": str(request_id),
            "question": question,
        }
    )
    selected = list(final.get("selected_agents") or select_agents(question, suggested))
    report = IntelligenceReport(
        report_id=str(uuid4()),
        run_id=str(run_id),
        question=_redact(question),
        executive_summary=bundle.summary or "Insufficient evidence.",
        findings=bundle.findings,
        insights=bundle.insights,
        recommendations=bundle.recommendations,
        evidence=bundle.evidence,
        contradictions=bundle.contradictions,
        limitations=bundle.limitations[:8],
        confidence=bundle.confidence,
        selected_agents=selected,
        generated_at=now or datetime.now(UTC),
    )
    logger.info(
        "intelligence_completed",
        run_id=str(run_id),
        request_id=str(request_id),
        merchant_id=str(tenant.merchant_id),
        store_id=str(tenant.store_id),
        selected_agents=report.selected_agents,
        recommendation_count=len(report.recommendations),
        contradiction_count=len(report.contradictions),
        token_input=bundle.token_input,
        token_output=bundle.token_output,
        model=bundle.model,
        success=True,
    )
    return report, bundle.token_input, bundle.token_output, bundle.model
