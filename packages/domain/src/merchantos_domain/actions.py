"""Proposal-shaped types only. ApprovedAction.load lands with the actions phase."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActionType(StrEnum):
    REDUCE_DISCOUNT_DEPTH = "reduce_discount_depth"
    UPDATE_VARIANT_PRICE = "update_variant_price"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_tool: str
    fact_id: str


class AgentActionProposal(BaseModel):
    """The only action-shaped object an agent may produce."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_type: ActionType
    resource_ids: tuple[UUID, ...]
    rationale: str
    evidence_refs: tuple[EvidenceRef, ...] = ()
