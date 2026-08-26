from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from merchantos_domain.agent_run import MAX_EVIDENCE_ITEMS, MAX_FINDINGS, EvidenceItem


class ClaimKind(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


class ConfidenceBand(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FindingSeverity(StrEnum):
    INFO = "info"
    WATCH = "watch"
    RISK = "risk"


class FindingCategory(StrEnum):
    REVENUE = "revenue"
    ORDERS = "orders"
    AOV = "aov"
    PRODUCT = "product"
    INVENTORY = "inventory"
    CUSTOMER = "customer"
    ANOMALY = "anomaly"
    OTHER = "other"


CONFIDENCE_SCORE = {
    ConfidenceBand.HIGH: 0.85,
    ConfidenceBand.MEDIUM: 0.55,
    ConfidenceBand.LOW: 0.25,
}


class Finding(BaseModel):
    """Grounded conclusion. Extra keys (tenant, approval) are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(max_length=32)
    title: str = Field(max_length=160)
    description: str = Field(max_length=800)
    category: FindingCategory
    severity: FindingSeverity
    claim_kind: ClaimKind
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    confidence: ConfidenceBand
    limitations: list[str] = Field(default_factory=list, max_length=4)


class AgentResult(BaseModel):
    """Primary specialist output. Not unstructured prose."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(max_length=32)
    run_id: str
    summary: str = Field(max_length=4000)
    findings: list[Finding] = Field(default_factory=list, max_length=MAX_FINDINGS)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)
    confidence: ConfidenceBand
    limitations: list[str] = Field(default_factory=list, max_length=8)
    tool_calls: list[str] = Field(default_factory=list, max_length=8)
