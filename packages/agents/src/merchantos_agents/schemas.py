from typing import Any, Literal

from merchantos_domain import (
    MAX_FINDINGS,
    ClaimKind,
    ConfidenceBand,
    EvidenceItem,
    FindingCategory,
    FindingSeverity,
)
from pydantic import BaseModel, ConfigDict, Field

ORCHESTRATOR_TOOLS = frozenset({"get_store_overview"})
SPECIALIST_NAME = Literal["analytics", "inventory", "customer"]


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)


class OrchestratorOutput(BaseModel):
    """Validated model output. Extra keys (tenant, approval, status) are rejected."""

    model_config = ConfigDict(extra="forbid")

    classification: Literal["commerce_question", "insufficient_data", "out_of_scope"]
    plan: str = Field(default="", max_length=2000)
    answer: str = Field(default="", max_length=4000)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.0, ge=0, le=1)
    next_steps: list[str] = Field(default_factory=list, max_length=8)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=16)
    insufficient_data: bool = False
    tool: ToolRequest | None = None
    specialist: SPECIALIST_NAME | None = None


class SpecialistPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: str = Field(default="", max_length=2000)
    tools: list[ToolRequest] = Field(default_factory=list, max_length=8)
    insufficient_data: bool = False


class FindingDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=160)
    description: str = Field(max_length=800)
    category: FindingCategory
    severity: FindingSeverity
    claim_kind: ClaimKind
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=4)


class SpecialistSynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(default="", max_length=4000)
    findings: list[FindingDraft] = Field(default_factory=list, max_length=MAX_FINDINGS)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    next_steps: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(default="", max_length=500)
    insufficient_data: bool = False
    proposed_confidence: ConfidenceBand = ConfidenceBand.MEDIUM
