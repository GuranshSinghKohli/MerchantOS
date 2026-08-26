from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from merchantos_domain.findings import ConfidenceBand, Finding


class AgentRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


TERMINAL_STATUSES = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

MAX_QUESTION_CHARS = 4000
MAX_EVIDENCE_ITEMS = 16
MAX_TOOL_RESULTS = 6
MAX_ERROR_ITEMS = 8
MAX_AGENT_ATTEMPTS = 3
MAX_SPECIALIST_TOOL_CALLS = 5
MAX_FINDINGS = 8


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(default="", max_length=32)
    source: str = Field(max_length=80)
    fact: str = Field(max_length=500)


class AskResult(BaseModel):
    """Merchant-safe structured run result. No tenant ids, tokens, or approvals."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(max_length=4000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(default="", max_length=500)
    confidence: float = Field(default=0.0, ge=0, le=1)
    next_steps: list[str] = Field(default_factory=list, max_length=8)
    insufficient_data: bool = False
    agent_name: str | None = Field(default=None, max_length=32)
    findings: list[Finding] = Field(default_factory=list, max_length=MAX_FINDINGS)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    confidence_band: ConfidenceBand | None = None
