"""Proposal, policy, snapshot, approval, and approved-action types.

Agents may produce AgentActionProposal only. ApprovedAction is loaded from
trusted rows after a merchant ApprovalRecord. There is no conversion path
from a proposal dict to ApprovedAction.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from merchantos_domain.errors import ForbiddenFactoryError, NotApprovedError
from merchantos_domain.ids import MerchantId, StoreId, UserId
from merchantos_domain.tenant import TenantContext

MAX_ACTION_RESOURCES = 1
MAX_ACTION_ATTEMPTS = 3
ACTION_TTL_HOURS = 24
MAX_TITLE_CHARS = 255
MAX_DESCRIPTION_CHARS = 5000
MAX_TAG_COUNT = 20
MAX_TAG_CHARS = 64
CRITICAL_RESOURCE_COUNT = 5
HIGH_RESOURCE_COUNT = 1

EXECUTABLE_ACTION_TYPES: frozenset[str] = frozenset(
    {
        "update_product_title",
        "update_product_description",
        "update_product_tags",
        "update_product_status",
    }
)


class ActionType(StrEnum):
    UPDATE_PRODUCT_TITLE = "update_product_title"
    UPDATE_PRODUCT_DESCRIPTION = "update_product_description"
    UPDATE_PRODUCT_TAGS = "update_product_tags"
    UPDATE_PRODUCT_STATUS = "update_product_status"
    REDUCE_DISCOUNT_DEPTH = "reduce_discount_depth"
    UPDATE_VARIANT_PRICE = "update_variant_price"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CONFLICT = "CONFLICT"


class ApprovalStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ShopifyMutation(StrEnum):
    UPDATE_PRODUCT_TITLE = "update_product_title"
    UPDATE_PRODUCT_DESCRIPTION = "update_product_description"
    UPDATE_PRODUCT_TAGS = "update_product_tags"
    UPDATE_PRODUCT_STATUS = "update_product_status"


class AuditEventType(StrEnum):
    ACTION_CREATED = "ACTION_CREATED"
    ACTION_VALIDATED = "ACTION_VALIDATED"
    ACTION_APPROVAL_REQUESTED = "ACTION_APPROVAL_REQUESTED"
    ACTION_APPROVED = "ACTION_APPROVED"
    ACTION_REJECTED = "ACTION_REJECTED"
    ACTION_QUEUED = "ACTION_QUEUED"
    ACTION_EXECUTING = "ACTION_EXECUTING"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    ACTION_FAILED = "ACTION_FAILED"
    ACTION_EXPIRED = "ACTION_EXPIRED"
    ACTION_CONFLICTED = "ACTION_CONFLICTED"
    ACTION_BLOCKED = "ACTION_BLOCKED"


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_tool: str = Field(max_length=80)
    fact_id: str = Field(max_length=80)


class AgentActionProposal(BaseModel):
    """The only action-shaped object an agent may produce."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_type: ActionType
    resource_ids: tuple[UUID, ...]
    rationale: str = Field(min_length=1, max_length=800)
    evidence_refs: tuple[EvidenceRef, ...] = ()

    @field_validator("resource_ids")
    @classmethod
    def _bounded_resources(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if not value:
            raise ValueError("resource_ids required")
        if len(value) > CRITICAL_RESOURCE_COUNT:
            raise ValueError("too many resources")
        return value


class IntendedProductChange(BaseModel):
    """Merchant- or service-supplied intended fields. Not a Shopify payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = Field(default=None, max_length=MAX_TITLE_CHARS)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_CHARS)
    tags: tuple[str, ...] | None = None
    status: Literal["ACTIVE", "DRAFT"] | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("title cannot be empty")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return value
        cleaned = tuple(item.strip() for item in value if item.strip())
        if len(cleaned) > MAX_TAG_COUNT:
            raise ValueError("too many tags")
        if any(len(item) > MAX_TAG_CHARS for item in cleaned):
            raise ValueError("tag too long")
        return cleaned


class PolicyDecision(BaseModel):
    """Produced only by PolicyService.evaluate (no LLMPort)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Literal["require_approval", "block"]
    risk_level: RiskLevel
    reasons: tuple[str, ...]
    required_scopes: tuple[str, ...]


class ActionSnapshot(BaseModel):
    """Built by SnapshotService from Postgres, never from the model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    before_state: dict[str, Any]
    after_state: dict[str, Any]
    payload: dict[str, Any]
    payload_hash: str
    affected_count: int


class ApprovalRecord(BaseModel):
    """Created only by ApprovalService.decide from a merchant session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    action_id: UUID
    merchant_id: MerchantId
    status: ApprovalStatus
    frozen_payload_hash: str
    decided_by: UserId
    decided_at: datetime


class ApprovedAction(BaseModel):
    """Loaded after Action.APPROVED + Approval.APPROVED. No LLM constructor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    approval_id: UUID
    merchant_id: MerchantId
    store_id: StoreId
    action_type: ActionType
    payload: dict[str, Any]
    payload_hash: str
    mutation: ShopifyMutation

    def __init__(self, **data: object) -> None:
        raise ForbiddenFactoryError("ApprovedAction must be created via load")

    @classmethod
    def model_validate(
        cls,
        obj: object,
        **kwargs: object,
    ) -> "ApprovedAction":
        raise ForbiddenFactoryError("ApprovedAction.model_validate is forbidden")

    @classmethod
    def load(
        cls,
        ctx: TenantContext,
        *,
        action_id: UUID,
        approval_id: UUID,
        action_status: str,
        approval_status: str,
        action_merchant_id: UUID,
        action_store_id: UUID,
        action_type: str,
        payload: dict[str, Any],
        payload_hash: str,
        frozen_payload_hash: str,
        expires_at: datetime | None,
        now: datetime,
    ) -> "ApprovedAction":
        if ctx.merchant_id != action_merchant_id or ctx.store_id != action_store_id:
            raise NotApprovedError("action does not belong to this tenant")
        if action_status not in {
            ActionStatus.APPROVED.value,
            ActionStatus.QUEUED.value,
            ActionStatus.EXECUTING.value,
            ActionStatus.COMPLETED.value,
        }:
            raise NotApprovedError("action is not approved")
        if approval_status != ApprovalStatus.APPROVED.value:
            raise NotApprovedError("approval is not approved")
        if payload_hash != frozen_payload_hash:
            raise NotApprovedError("payload hash mismatch")
        if expires_at is not None and expires_at <= now:
            raise NotApprovedError("action has expired")
        if action_type not in EXECUTABLE_ACTION_TYPES:
            raise NotApprovedError("action type is not executable")
        return cls.model_construct(
            action_id=action_id,
            approval_id=approval_id,
            merchant_id=MerchantId(action_merchant_id),
            store_id=StoreId(action_store_id),
            action_type=ActionType(action_type),
            payload=payload,
            payload_hash=payload_hash,
            mutation=ShopifyMutation(action_type),
        )


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    mutation_name: str
    shopify_request_id: str | None = None
    error_code: str | None = None
    verified: bool = False
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    response_redacted: dict[str, Any] = Field(default_factory=dict)


class ActionExecution(BaseModel):
    """Worker-owned execution record. Not constructible from a proposal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    status: ActionStatus
    attempt: int = 0
    result: ActionResult | None = None


class ActionAuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID
    merchant_id: MerchantId
    actor_type: str
    actor_id: str | None = None
    event_type: AuditEventType
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


MUTATION_FOR_TYPE = {
    ActionType.UPDATE_PRODUCT_TITLE: ShopifyMutation.UPDATE_PRODUCT_TITLE,
    ActionType.UPDATE_PRODUCT_DESCRIPTION: ShopifyMutation.UPDATE_PRODUCT_DESCRIPTION,
    ActionType.UPDATE_PRODUCT_TAGS: ShopifyMutation.UPDATE_PRODUCT_TAGS,
    ActionType.UPDATE_PRODUCT_STATUS: ShopifyMutation.UPDATE_PRODUCT_STATUS,
}

ACTION_RISK_TABLE: dict[ActionType, tuple[RiskLevel, RiskLevel]] = {
    ActionType.UPDATE_PRODUCT_TITLE: (RiskLevel.MEDIUM, RiskLevel.HIGH),
    ActionType.UPDATE_PRODUCT_DESCRIPTION: (RiskLevel.MEDIUM, RiskLevel.HIGH),
    ActionType.UPDATE_PRODUCT_TAGS: (RiskLevel.MEDIUM, RiskLevel.HIGH),
    ActionType.UPDATE_PRODUCT_STATUS: (RiskLevel.MEDIUM, RiskLevel.HIGH),
    ActionType.UPDATE_VARIANT_PRICE: (RiskLevel.HIGH, RiskLevel.CRITICAL),
    ActionType.REDUCE_DISCOUNT_DEPTH: (RiskLevel.HIGH, RiskLevel.CRITICAL),
}
