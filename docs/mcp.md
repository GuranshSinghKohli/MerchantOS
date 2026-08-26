# MerchantOS MCP Tool Layer

**Status:** Accepted (post-remediation)  
**Related:** [contracts.md](contracts.md), [ADR 0004](adr/0004-mcp-in-process-registry.md), [ADR 0012](adr/0012-capability-isolated-workers.md), [ADR 0016](adr/0016-deterministic-action-snapshots.md)

Agents interact with the world only through typed **read and propose** tools. There is no generic HTTP, SQL, Shopify, or execute tool.

## Architecture

```
Agent
  → ToolPort.for_agent(name)
      → allowlist check (ToolNotAllowed)
      → Inject TenantContext (from job row / session)
      → Permission + Pydantic validation
      → Application service
      → Repository (tenant enforced)
      → Redacted tool_calls + audit_events
```

`execute_approved_action` **does not exist**. Execution is `ExecutionWorker` → `ApprovedAction.load` → `ShopifyMutator`.

## Allowlists

Runtime `AGENT_TOOLS` frozensets (see contracts). Binding the full registry to a node is forbidden.

## Common rules

| Field | Rule |
|-------|------|
| Tenant | Injected; strip any model-supplied tenant id; no tenant field on input schemas |
| I/O | Pydantic → JSON Schema |
| Timeout | Enforced; `TOOL_TIMEOUT` |
| Retry | Worker may retry **read** timeouts |
| Audit | Redacted I/O on every call |
| Unknown name | Error — no HTTP fallback |

Permissions: `commerce.read`, `recommendation.write`, `action.propose`.  
(`action.execute` is not a tool permission.)

Risk on **propose** is assigned later by PolicyService, not by the tool based on model text.

## Tool catalog

Read tools are unchanged in spirit (`get_store_context` … `get_sales_trends`, `search_merchant_knowledge`). None accept `tenant_id`. Timeouts as before. Metrics computed in application code.

### create_recommendation

- In: `{ problem, evidence, hypothesis, proposed_action, expected_impact, confidence, risks, affected_resources, measurement_plan }`
- **Not in input:** `approval_required`, `tenant_id`, `status`
- Out: `{ recommendation_id }`
- Permission: `recommendation.write` · Timeout: 3s
- Agents: `strategy` only

### create_action_plan

- In: `{ recommendation_id, action_type: ActionType, resource_ids: UUID[], rationale, evidence_refs }`
- **Not in input:** `params` blob, `before_state`, `after_state`, `risk_level`, `payload`, `status`
- Behavior: `SnapshotService` builds snapshot from DB; `PolicyService.evaluate`; persist `Action.PROPOSED` or `BLOCKED`
- Out: `{ action_id, status: "PROPOSED"|"BLOCKED", risk_level, before_state, after_state }` (server-authored)
- Permission: `action.propose` · Timeout: 5s
- Agents: `action_planner` only
- Errors: `UNKNOWN_ACTION_TYPE`, `RESOURCE_NOT_FOUND`, `CRITICAL_BLOCKED`

### validate_action — removed as an agent tool

PolicyService is called by the application service inside `create_action_plan` (and can be called from the approve API for a re-check). Agents do not invoke policy.

## What will never exist

- `execute_approved_action`
- `raw_shopify_graphql`
- `execute_sql`
- `http_request`
- `run_shell`
- Any tool that accepts a tenant id
- Any tool that accepts `status: APPROVED`

## Tests

- Registry used by agent handler raises on `execute_approved_action`
- `create_action_plan` with extra `payload` / `status` fields fails schema validation
- Persisted snapshot ignores any model-supplied after_state
- `ToolPort.for_agent("analytics")` cannot call `create_action_plan`
