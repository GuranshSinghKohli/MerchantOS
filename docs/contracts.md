# MerchantOS Invariant Contracts

**Status:** Accepted  
**Canonical principles:** [`SYSTEM_DESIGN.md`](../SYSTEM_DESIGN.md)  
**Related:** [ADR 0012](adr/0012-capability-isolated-workers.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md), [ADR 0014](adr/0014-tenant-from-job-row.md)

These types must exist in `packages/domain`. They are not documentation. Implementations that cannot express a bypass are required. Tests listed here are mandatory when the corresponding package lands.

## 1. Invariant

```
THE LLM MUST NEVER BE ABLE TO AUTHORIZE, APPROVE, OR EXECUTE
A MUTATING SHOPIFY ACTION.
```

Enforced path:

```
Authenticated merchant session
    → ActionProposal (agent or planner, untrusted)
    → PolicyService.evaluate (deterministic, no LLM)
    → Action row status=PROPOSED | BLOCKED
    → Merchant POST /api/v1/approvals/{action_id}/approve
    → ApprovalRecord + Action status=APPROVED (one transaction)
    → outbox → execution queue
    → ExecutionWorker (no LLM, no agent tools)
    → ShopifyPort.mutate(ApprovedAction)
    → ActionResult + AuditEvent
```

There is no `execute_approved_action` MCP tool. There is no `ApprovedAction` constructor callable from agent code.

## 2. TenantContext

```python
# Conceptual — packages/domain/tenant.py

class TenantContext(FrozenModel):
    merchant_id: MerchantId
    store_id: StoreId
    user_id: UserId | None
    request_id: RequestId
    scopes: tuple[ShopifyScope, ...]

    # The only legal factories:
    @classmethod
    def from_session(cls, session: SessionRow) -> TenantContext: ...

    @classmethod
    def from_job_row(cls, row: AgentRun | SyncJob | Action) -> TenantContext: ...

# Forbidden (must not exist):
#   TenantContext(merchant_id=llm_output["tenant_id"])
#   TenantContext.from_tool_args(...)
#   TenantContext.from_agent_state(...)
#   TenantContext.from_queue_message(...)
```

Queue messages:

```python
class QueueMessage(FrozenModel):
    job_kind: Literal["agent_run", "sync", "webhook", "action_execute"]
    job_id: UUID
    traceparent: str | None
    # NO merchant_id, store_id, token, scopes
```

**Tests**

- Constructing `TenantContext` from a dict that includes a model-supplied id is a type/lint failure or raises `ForbiddenFactoryError`.
- Worker that builds context from a queue body fails a contract test.
- Repository method without `TenantContext` is a type error.

## 3. Proposal vs approval vs execution

```python
class ActionType(Enum):
    # Allowlist only. Adding a member requires a policy table row.
    REDUCE_DISCOUNT_DEPTH = "reduce_discount_depth"
    UPDATE_VARIANT_PRICE = "update_variant_price"
    # no DELETE_*, no BULK_* in V1

class AgentActionProposal(FrozenModel):
    """The only action-shaped object an agent may produce."""
    action_type: ActionType
    resource_ids: tuple[UUID, ...]
    rationale: str
    evidence_refs: tuple[EvidenceRef, ...]
    # Forbidden fields (must not exist on this type):
    # status, approval_id, approved, tenant_id, payload, before_state,
    # after_state, risk_level, permissions, shopify_input

class PolicyDecision(FrozenModel):
    """Produced only by PolicyService.evaluate (no LLMPort)."""
    verdict: Literal["require_approval", "block"]
    # "allow" does not exist — it previously implied Shopify execute
    risk_level: RiskLevel  # from ACTION_RISK_TABLE[type] + len(resource_ids)
    reasons: tuple[str, ...]
    required_scopes: tuple[ShopifyScope, ...]

class ActionSnapshot(FrozenModel):
    """Built by SnapshotService from Postgres, never from the model."""
    before_state: JsonObject
    after_state: JsonObject
    payload: JsonObject          # typed per ActionType
    payload_hash: Sha256
    affected_count: int

class ApprovalRecord(FrozenModel):
    """Created only by ApprovalService.decide(session, action_id, decision)."""
    id: ApprovalId
    action_id: ActionId
    merchant_id: MerchantId      # copied from session, not from body
    status: Literal["APPROVED", "REJECTED"]
    frozen_payload_hash: Sha256
    decided_by: UserId
    decided_at: datetime

class ApprovedAction(FrozenModel):
    """Loaded by ExecutionWorker from DB after APPROVED. No public ctor from LLM."""
    action_id: ActionId
    approval_id: ApprovalId
    merchant_id: MerchantId
    store_id: StoreId
    payload: JsonObject
    payload_hash: Sha256
    mutation: ShopifyMutation    # mapped from ActionType in code

    @classmethod
    def load(cls, ctx: TenantContext, action_id: ActionId) -> ApprovedAction:
        """Raises NotApprovedError unless Action.APPROVED and Approval.APPROVED
        and hashes match and not expired."""
```

`packages/agents` may import `AgentActionProposal` only. Importing `ApprovalRecord`, `ApprovedAction`, or `ShopifyPort.mutate` from `packages/agents` is a forbidden import (enforced by a layer test / import-linter).

**Tests**

- Agent package import of `ApprovedAction` or `ShopifyMutator` fails CI.
- `PolicyService.evaluate` does not accept `LLMPort`.
- `ApprovalService.decide` requires `TenantContext.from_session`; a worker context is rejected.
- `ApprovedAction.load` on `PROPOSED` / `REJECTED` / hash mismatch / expiry raises.
- LLM-shaped dict with `status: "APPROVED"` cannot construct `ApprovedAction`.

## 4. PolicyService (not an agent)

```python
class PolicyService:
    def evaluate(
        self,
        ctx: TenantContext,
        proposal: AgentActionProposal,
        snapshot: ActionSnapshot,
    ) -> PolicyDecision:
        ...
    # no llm argument
```

Risk table (code, not prompt):

| ActionType | Count 1 | Count > N (N=5 V1) |
|------------|---------|---------------------|
| UPDATE_VARIANT_PRICE | HIGH | CRITICAL (block) |
| REDUCE_DISCOUNT_DEPTH | HIGH | CRITICAL (block) |
| Internal insight only | n/a (not an ActionType) | |

MEDIUM types, when added, also `require_approval`. CRITICAL always `block`.

`create_recommendation` must **not** include `approval_required`. Strategy may suggest that an action is needed; PolicyService decides.

## 5. Capability sets (workers)

```python
class AgentCapabilities:
    tools: ToolRegistry          # read + propose only
    llm: LLMPort
    runs: AgentRunRepository
    # no ShopifyMutator, no CredentialStore, no Engine.execute

class ExecutionCapabilities:
    shopify: ShopifyMutator      # mutate() only
    actions: ActionRepository
    audit: AuditWriter
    # no LLMPort, no ToolRegistry, no CredentialStore.raw_token()

class SyncCapabilities:
    shopify: ShopifyReader       # read/paginate only
    projection: ProjectionWriter
    # no mutate(), no LLMPort

class WebhookCapabilities:
    verifier: WebhookVerifier
    projection: ProjectionWriter
    # no mutate(), no LLMPort
```

Factories take an explicit `JobKind`. A single “god” capability object must not exist.

`ShopifyMutator` and `ShopifyReader` are separate interfaces. The agent process never receives `ShopifyMutator`.

`CredentialStore` is only visible inside `packages/shopify` adapter construction, not to handlers.

**Tests**

- `AgentJobHandler` constructed with `ExecutionCapabilities` is a type error.
- Registry used by agents raises `UnknownTool` for `execute_approved_action` (that name must not be registered).
- Sync handler calling `mutate` is a type error.

## 6. Tool registry allowlists

Phase 5 registers read tools only ([ADR 0021](adr/0021-mcp-read-permissions.md)). `strategy` / `action_planner` allowlists land with propose tools.

```python
AGENT_TOOLS: dict[AgentName, frozenset[ToolName]] = {
    "orchestrator": frozenset({"get_store_overview"}),
    "analytics": frozenset({
        "get_store_overview", "get_revenue_metrics", "get_order_metrics",
        "get_product_performance", "get_sales_trends",
        "get_merchant_health", "get_opportunities",
    }),
    "inventory": frozenset({"get_inventory_health", "get_product_performance"}),
    "customer": frozenset({"get_customer_metrics"}),
}

# policy is not an agent and has no tools
# execute_* is not a tool
# Phase 6 (not registered): strategy create_recommendation / search_merchant_knowledge
# Phase 6 (not registered): action_planner create_action_plan
```

`ToolPort.for_agent(name)` returns a proxy that raises `ToolNotAllowed` for any other name. Binding “all tools” to a node is forbidden.

`create_action_plan` input is `AgentActionProposal` fields only. It calls SnapshotService + PolicyService and persists `Action(PROPOSED|BLOCKED)`. It cannot persist `APPROVED`.

## 7. Outbox and leases

```python
class OutboxMessage:
    id: UUID
    job_kind: JobKind
    job_id: UUID
    created_at: datetime
    published_at: datetime | None

# Same transaction as the business write:
#   INSERT agent_runs ... PENDING
#   INSERT outbox_messages ...
# Publisher relays to SQS; at-least-once publish is OK because job_id is idempotent.
```

Leases:

```python
# AgentRun PENDING → RUNNING only via
#   UPDATE ... SET status=RUNNING, lease_owner, lease_until
#   WHERE id=? AND status=PENDING
# Rows still RUNNING after lease_until are reaped to FAILED or retried once.

# Action EXECUTING uses the same lease pattern.
# Visibility timeout >= max(lease, 2 * max_runtime).
```

## 8. Layer import rules

| Package | May import | Must not import |
|---------|------------|-----------------|
| `domain` | stdlib, pydantic | fastapi, sqlalchemy, shopify, openai, mcp runtime |
| `app` | domain, ports | fastapi, openai SDK, shopify SDK |
| `agents` | domain (proposals, TenantContext), llm port, tool port | `ApprovedAction`, `ShopifyMutator`, `CredentialStore`, sqlalchemy |
| `mcp` | domain, app services | `ShopifyMutator`, raw httpx |
| `shopify` | domain ports | agents, llm |
| `api` | app, observability | agents, shopify adapter internals |
| `worker.agent` | AgentCapabilities | ExecutionCapabilities |
| `worker.execution` | ExecutionCapabilities | LLMPort, ToolRegistry |

Enforced with import-linter (or equivalent) in CI once packages exist.

## 9. Compensating controls if a type is bypassed in a bug

These do not replace the types. They are defense in depth:

- DB check: `ApprovedAction.load` requires `Action.APPROVED` + `Approval.APPROVED` + hash match
- RLS + `TenantContext`
- Trigger: `actions.payload` immutable after `PROPOSED` snapshot is written
- Trigger: `approvals` INSERT only from a role used by `ApprovalService` (app role), not a generic writer — if RLS roles are too heavy for V1, the service + tests are the control and this is documented as a follow-up
