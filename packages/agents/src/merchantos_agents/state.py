from typing import Any

from merchantos_domain import (
    MAX_ERROR_ITEMS,
    MAX_EVIDENCE_ITEMS,
    MAX_FINDINGS,
    MAX_QUESTION_CHARS,
    MAX_TOOL_RESULTS,
    AgentRunStatus,
    ConfidenceBand,
    EvidenceItem,
    Finding,
)
from pydantic import BaseModel, ConfigDict, Field


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=80)
    ok: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class AgentState(BaseModel):
    """Graph-writable state. Tenant and secrets are not fields."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    request_id: str
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    classification: str | None = None
    agent_name: str | None = Field(default=None, max_length=32)
    plan: str | None = Field(default=None, max_length=2000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=MAX_EVIDENCE_ITEMS)
    tool_results: list[ToolResult] = Field(default_factory=list, max_length=MAX_TOOL_RESULTS)
    findings: list[Finding] = Field(default_factory=list, max_length=MAX_FINDINGS)
    answer: str | None = Field(default=None, max_length=4000)
    assumptions: list[str] = Field(default_factory=list, max_length=8)
    uncertainty: str | None = Field(default=None, max_length=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_band: ConfidenceBand | None = None
    next_steps: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    errors: list[str] = Field(default_factory=list, max_length=MAX_ERROR_ITEMS)
    status: AgentRunStatus = AgentRunStatus.RUNNING
    insufficient_data: bool = False
    llm_retries: int = 0
    token_input: int = 0
    token_output: int = 0
    model: str | None = None

    def as_graph(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
