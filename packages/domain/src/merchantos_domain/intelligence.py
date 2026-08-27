from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from merchantos_domain.agent_run import MAX_FINDINGS, EvidenceItem
from merchantos_domain.findings import ConfidenceBand, Finding

MAX_INSIGHTS = 8
MAX_RECOMMENDATIONS = 6
MAX_CONTRADICTIONS = 8
MAX_INTEL_AGENTS = 3
MAX_INTEL_EVIDENCE = 24


class RunKind(StrEnum):
    ASK = "ask"
    INTELLIGENCE = "intelligence"


class InsightKind(StrEnum):
    OBSERVATION = "OBSERVATION"
    CORRELATION = "CORRELATION"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


class RecommendationPriority(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(max_length=32)
    metric: str = Field(max_length=80)
    left_source: str = Field(max_length=80)
    left_fact: str = Field(max_length=500)
    right_source: str = Field(max_length=80)
    right_fact: str = Field(max_length=500)
    status: str = Field(default="unresolved", max_length=32)


class CrossAgentInsight(BaseModel):
    """Cross-domain conclusion. Extra keys (tenant, approval, execute) are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(max_length=32)
    title: str = Field(max_length=160)
    description: str = Field(max_length=800)
    kind: InsightKind
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    finding_ids: list[str] = Field(default_factory=list, max_length=8)
    agent_names: list[str] = Field(default_factory=list, max_length=3)
    confidence: ConfidenceBand
    limitations: list[str] = Field(default_factory=list, max_length=4)


class Recommendation(BaseModel):
    """Advisory only. Cannot carry approval, mutation, or execute fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(max_length=32)
    title: str = Field(max_length=160)
    recommendation: str = Field(max_length=800)
    rationale: str = Field(max_length=800)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    insight_ids: list[str] = Field(default_factory=list, max_length=8)
    finding_ids: list[str] = Field(default_factory=list, max_length=8)
    expected_objective: str = Field(max_length=240)
    priority: RecommendationPriority
    confidence: ConfidenceBand
    limitations: list[str] = Field(default_factory=list, max_length=4)


class IntelligenceReport(BaseModel):
    """Merchant-safe intelligence output. No tenant ids, tokens, or approvals."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    run_id: str
    question: str = Field(max_length=4000)
    executive_summary: str = Field(max_length=4000)
    findings: list[Finding] = Field(default_factory=list, max_length=MAX_FINDINGS)
    insights: list[CrossAgentInsight] = Field(default_factory=list, max_length=MAX_INSIGHTS)
    recommendations: list[Recommendation] = Field(
        default_factory=list, max_length=MAX_RECOMMENDATIONS
    )
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=MAX_INTEL_EVIDENCE)
    contradictions: list[Contradiction] = Field(default_factory=list, max_length=MAX_CONTRADICTIONS)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    confidence: ConfidenceBand
    selected_agents: list[str] = Field(default_factory=list, max_length=MAX_INTEL_AGENTS)
    generated_at: datetime
