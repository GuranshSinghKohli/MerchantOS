from inspect import signature

from merchantos_domain import (
    ACTION_RISK_TABLE,
    EXECUTABLE_ACTION_TYPES,
    ActionSnapshot,
    AgentActionProposal,
    PolicyDecision,
    RiskLevel,
    TenantContext,
)
from merchantos_domain.actions import CRITICAL_RESOURCE_COUNT

HIGH_COUNT = 1


class PolicyService:
    """Deterministic risk and verdict. No LLMPort."""

    def evaluate(
        self,
        ctx: TenantContext,
        proposal: AgentActionProposal,
        snapshot: ActionSnapshot,
    ) -> PolicyDecision:
        count = snapshot.affected_count or len(proposal.resource_ids)
        single, many = ACTION_RISK_TABLE[proposal.action_type]
        if count > CRITICAL_RESOURCE_COUNT:
            risk = RiskLevel.CRITICAL
        elif count > HIGH_COUNT:
            risk = many
        else:
            risk = single
        if risk is RiskLevel.CRITICAL:
            return PolicyDecision(
                verdict="block",
                risk_level=risk,
                reasons=("CRITICAL actions are blocked in V1",),
                required_scopes=(),
            )
        if proposal.action_type.value not in EXECUTABLE_ACTION_TYPES:
            return PolicyDecision(
                verdict="block",
                risk_level=risk,
                reasons=("action type is not executable in Phase 9",),
                required_scopes=(),
            )
        scopes = ("write_products", "read_products")
        if "write_products" not in ctx.scopes:
            return PolicyDecision(
                verdict="block",
                risk_level=risk,
                reasons=("write_products scope is required",),
                required_scopes=scopes,
            )
        return PolicyDecision(
            verdict="require_approval",
            risk_level=risk,
            reasons=("MEDIUM and HIGH Shopify writes require merchant approval",),
            required_scopes=scopes,
        )


def policy_has_no_llm_parameter() -> bool:
    return "llm" not in signature(PolicyService.evaluate).parameters
