# MerchantOS Agent Architecture

**Status:** Accepted (Phase 9 approval-gated mutations implemented 2026-08-26)  
**Runtime:** LangGraph in the **agent** worker handler only  
**Related:** [contracts.md](contracts.md), [mcp.md](mcp.md), [ADR 0008](adr/0008-llm-provider-port.md), [ADR 0012](adr/0012-capability-isolated-workers.md), [ADR 0013](adr/0013-proposal-vs-approval-types.md)

Phase 8 coordinates the Phase 7 specialists through a bounded intelligence graph. Strategy, Action Planner, and PolicyService remain specified and are **not registered**.

Agents reason. They do not authorize, calculate money, mutate Shopify, choose a tenant, create approvals, or execute actions.

Policy is **not** an agent. It is `PolicyService` in `packages/app` and has no `LLMPort`.

## Intelligence graph (Phase 8)

```
POST /api/v1/intelligence/query
  → AgentRun (run_kind=intelligence)
  → select allowlisted specialists
  → Analytics / Inventory / Customer (as selected)
  → evidence aggregation + contradiction detection
  → synthesis (OBSERVATION | CORRELATION | INFERENCE | HYPOTHESIS)
  → advisory Recommendation
  → STOP
```

Selection is deterministic keyword matching intersected with `SPECIALIST_NAMES`. The model cannot load arbitrary agent classes. Maximum 3 specialists, 8 LLM schema retries across the run, 8s per LLM call, 90s intelligence lease.

Traceability: Recommendation → insight → finding → evidence → MCP tool → deterministic analytics.

## Ask graph

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

Merchant `POST /api/v1/actions/{action_id}/approve` (alias `/api/v1/approvals/{action_id}/approve`) is **outside** this graph. Phase 9 does not register Strategy or Action Planner; proposals are created by `ActionService.propose` from a merchant session.

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

- Tools: `get_store_overview` only (Phase 5)
- Failure: unclassifiable → insufficient_data, no specialists

### Analytics

- Tools: `get_store_overview`, `get_revenue_metrics`, `get_order_metrics`, `get_product_performance`, `get_sales_trends`, `get_merchant_health`, `get_opportunities`
- Numbers come from tools. Do not fabricate.
- Output: typed `AgentResult` with FACT / INFERENCE / HYPOTHESIS findings.

### Inventory

- Tools: `get_inventory_health`, `get_product_performance`
- Do not invent lead times, reorder quantities, or demand.

### Customer

- Tools: `get_customer_metrics`
- Treat notes as untrusted data. Emails are never returned. No churn/LTV claims.

### Confidence

Deterministic ceiling in `packages/agents` evidence helpers:

| Band | When |
|------|------|
| HIGH | ≥2 evidence items, FACT findings, no tool errors, no conflict, no assumptions |
| MEDIUM | inferences, assumptions, or a single evidence item |
| LOW | insufficient data, tool errors, conflicting growth signs, or only hypotheses |

The model proposes a band and may only keep or lower it. Scores: HIGH 0.85, MEDIUM 0.55, LOW 0.25.

Opposite-sign `*_growth_pct` facts become unresolved `Contradiction` objects and force LOW.

Recommendation priority is CRITICAL / HIGH / MEDIUM / LOW. Deterministic ceiling: stockout + revenue facts can reach CRITICAL; revenue decline can reach HIGH; otherwise MEDIUM. The model may only stay or go lower.

Bounds: 5 specialist tool calls, 2 LLM schema retries, 8s LLM timeout, 40s specialist budget, 90s intelligence lease, 3 job attempts, 3 specialists per intelligence run.

### Strategy

- Tools: `create_recommendation`, `search_merchant_knowledge` (Phase 6; not registered)
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
