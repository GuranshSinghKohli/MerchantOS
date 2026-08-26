# MerchantOS MCP Tool Layer

**Status:** Accepted (Phase 5 implemented 2026-08-26)  
**Related:** [contracts.md](contracts.md), [ADR 0004](adr/0004-mcp-in-process-registry.md), [ADR 0012](adr/0012-capability-isolated-workers.md), [ADR 0014](adr/0014-tenant-from-job-row.md), [ADR 0021](adr/0021-mcp-read-permissions.md)

Agents interact with the world only through typed **read** tools. Phase 7 specialists use the Phase 5 registry via `ToolPort.for_agent`. Propose tools remain unregistered. There is no generic HTTP, SQL, Shopify, or execute tool.

## Architecture

```
Future Agent
  → ToolRegistry.for_agent(name)
      → allowlist check (ToolNotAllowed)
      → TenantContext (from_session / from_job_row only)
      → strip model-supplied tenant fields
      → permission + Pydantic validation
      → AnalyticsService
      → AnalyticsRepository (tenant enforced)
      → redacted tool_invoked log
```

The MCP layer is an interface. It does not recompute analytics or issue SQL.

`execute_approved_action` **does not exist**. Execution remains `ExecutionWorker` → `ApprovedAction.load` → `ShopifyMutator` (later phase).

## Allowlists

Runtime `AGENT_TOOLS` frozensets live in `packages/mcp`. Binding the full registry to a node is forbidden. Only explicitly registered tools may be invoked.

Phase 5 agent allowlists (read tools only):

| Agent | Tools |
|-------|-------|
| orchestrator | `get_store_overview` |
| analytics | overview, revenue, orders, product performance, sales trends, health, opportunities |
| inventory | `get_inventory_health`, `get_product_performance` |
| customer | `get_customer_metrics` |

Phase 7 binds analytics, inventory, and customer. `strategy` and `action_planner` are not bound until propose tools exist.

## Common rules

| Field | Rule |
|-------|------|
| Tenant | Injected; strip any model-supplied tenant id; no tenant field on input schemas |
| I/O | Pydantic → JSON Schema; `extra=forbid` on inputs |
| Timeout | Enforced per tool (Phase 5: 5s) |
| Retry | Worker may retry **read** timeouts (when agents exist) |
| Audit | Redacted I/O on every `tool_invoked` |
| Unknown name | `UnknownTool` — no HTTP/SQL fallback |

Permissions ([ADR 0021](adr/0021-mcp-read-permissions.md)): `analytics:read`, `products:read`, `inventory:read`, `orders:read`, `customers:read`.  
(`action.execute` is not a tool permission.)

All Phase 5 tools are `READ_ONLY` / `LOW` risk. Future mutation tools must use the approval/action architecture.

## Phase 5 tool catalog

Every tool: tenant required, timeout 5s, `extra=forbid` inputs, no `tenant_id` / `merchant_id` / `store_id` fields. Filters: `preset`, `compare`, optional `from`/`to` (custom requires both; max 366 days). Product performance also accepts `limit` (1–100), `offset` (≤ 10000), `sort`.

| Tool | Permission | Output (bounded) |
|------|------------|------------------|
| `get_store_overview` | `analytics:read` | KPIs, trends, health, opportunities |
| `get_revenue_metrics` | `analytics:read` | KPIs, daily revenue trend |
| `get_order_metrics` | `orders:read` | Order counts, daily trend |
| `get_product_performance` | `products:read` | Paginated product rows |
| `get_inventory_health` | `inventory:read` | Inventory coverage |
| `get_customer_metrics` | `customers:read` | New/returning counts (no emails) |
| `get_sales_trends` | `analytics:read` | Daily revenue and customer series |
| `get_merchant_health` | `analytics:read` | Health score and components |
| `get_opportunities` | `analytics:read` | Deterministic opportunity list |

Outputs are JSON-schema validated. Extra service fields are dropped. Tokens, emails, and stack traces are not returned.

### Phase 6 (not registered)

`create_recommendation`, `create_action_plan`, and `search_merchant_knowledge` remain specified in planning docs. They are not in the Phase 5 registry.

## Errors

Typed `ToolError` codes: `invalid_input`, `unauthorized`, `forbidden`, `tenant_mismatch`, `not_found`, `timeout`, `dependency_failure`, `rate_limit`, `internal_failure`, `unknown_tool`, `tool_not_allowed`. Messages are agent-safe. Causes are chained for operators; they are not serialized to callers.

## What will never exist

- `execute_approved_action`
- `raw_shopify_graphql`
- `execute_sql`
- `http_request`
- `run_shell`
- Any tool that accepts a tenant id
- Any tool that accepts `status: APPROVED`
- Dynamic discovery of arbitrary Python functions

## Tests

- Registered tools are discoverable; unregistered and forbidden names raise `UnknownTool`
- Extra fields, SQL/HTTP-shaped arguments, and oversized limits fail validation
- Tenant fields in arguments are stripped; Tenant A cannot read Tenant B
- Permission checks and agent allowlists fail closed
- Timeouts, dependency failures, and output-schema failures are typed
- Source scan: MCP package has no SQL/HTTP/shell/Shopify mutator escape hatches
