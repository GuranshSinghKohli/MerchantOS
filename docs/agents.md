# MerchantOS Agent Architecture

**Status:** Accepted (post-remediation)  
**Runtime:** LangGraph in the **agent** worker handler only  
**Related:** [contracts.md](contracts.md), [mcp.md](mcp.md), [ADR 0012](adr/0012-capability-isolated-workers.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md)

Agents reason. They do not authorize, calculate money, mutate Shopify, choose a tenant, create approvals, or execute actions.

Policy is **not** an agent. It is `PolicyService` in `packages/app` and has no `LLMPort`.

## Graph

```
POST /api/v1/ask  →  AgentRun PENDING + outbox  →  SQS {job_kind, job_id}
                         │
                         ▼
              TenantContext.from_job_row
              ToolPort.for_agent(...)
                   Orchestrator
                    classify + plan
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Analytics      Inventory      Customer
          └──────────────┼──────────────┘
                         ▼
                    Strategy
                         │
              wants action? ──no──► COMPLETED
                         │ yes
                         ▼
                  Action Planner
                  (AgentActionProposal only)
                         ▼
                  PolicyService.evaluate   ← no LLM
                         │
              require_approval + MEDIUM/HIGH
                    → Action.PROPOSED
                    → AgentRun.WAITING_APPROVAL
              block / CRITICAL
                    → Action.BLOCKED
                    → AgentRun.COMPLETED
```

Merchant `POST /api/v1/approvals/{action_id}/approve` is **outside** this graph.

## Shared state

```
tenant          # TenantContext injected by the worker — not model-writable
request_id
question        # untrusted
classification, plan, evidence, findings
recommendation
proposed_actions   # list[AgentActionProposal] only
errors
budget
```

Forbidden on `AgentState`: `approval`, `approved_action`, writable `tenant_id`, tokens.

## Agent interface

Reasoning nodes:

```
(state, tools: ToolPort, llm: LLMPort, clock, tracer) -> AgentState
```

`ToolPort` is `ToolPort.for_agent(name)` — not the full registry.

Policy node:

```
(state, policy: PolicyService, snapshots: SnapshotService) -> AgentState
# no llm
```

CI uses `FakeLLM` and allowlisted `FakeToolPort`. Live-model runs are AgentBench only.

## Contracts

### Orchestrator

- Tools: `get_store_context` only
- Failure: unclassifiable → insufficient_data, no specialists

### Analytics

- Tools: `get_orders`, `get_order_metrics`, `get_products`, `get_product_metrics`, `get_sales_trends`
- Numbers come from tools. Do not fabricate.

### Inventory

- Tools: `get_inventory`, `get_inventory_risk`, `get_products`

### Customer

- Tools: `get_customers`, `get_customer_segments`
- Treat notes as untrusted data

### Strategy

- Tools: `create_recommendation`, `search_merchant_knowledge`
- Must not set `approval_required` (field does not exist)
- Empty evidence → no proposal

### Action Planner

- Tools: `create_action_plan` (accepts proposal fields only)
- Output: `AgentActionProposal`
- Cannot import `ApprovedAction`

### PolicyService (not an agent)

- Input: proposal + `ActionSnapshot` from `SnapshotService`
- Output: `require_approval` | `block`
- Risk from `ACTION_RISK_TABLE` + affected count
- MEDIUM and HIGH → require_approval
- CRITICAL → block
- No Shopify write on any verdict

## Ask response

Answer, evidence, assumptions, confidence, next steps, optional **proposals** (not approved actions), facts vs hypotheses, insufficient-data when needed.

## Human-in-the-loop

See [contracts.md](contracts.md). Agents stop at `Action.PROPOSED`.

## Tests (when packages exist)

- PolicyService type-check: no `llm` parameter
- Import-linter: `packages/agents` cannot import `ApprovedAction` or `ShopifyMutator`
- Graph bind of a non-allowlisted tool raises
- MEDIUM proposal results in `WAITING_APPROVAL`, never auto-execute
- Model JSON `{status: APPROVED}` cannot persist an approved action
