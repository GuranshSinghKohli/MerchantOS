# ADR 0021 — Resource-scoped MCP read permissions and Phase 5 tool catalog

- **Status:** Accepted
- **Date:** 2026-08-26
- **Does not change** [0004](0004-mcp-in-process-registry.md) (in-process registry), [0009](0009-server-injected-tenant-context.md) / [0014](0014-tenant-from-job-row.md) (trusted tenant), or [0012](0012-capability-isolated-workers.md) (no execute tool)

## Context

Planning docs used a single `commerce.read` permission and placeholder read-tool names (`get_store_context`, `get_orders`, …) before analytics existed. Phase 5 exposes deterministic Phase 4 analytics through MCP. A generic permission would let any read-capable agent call every commerce tool.

## Decision

1. Each Phase 5 tool declares the minimum resource permission:
   - `analytics:read`
   - `products:read`
   - `inventory:read`
   - `orders:read`
   - `customers:read`
2. Registered read tools match implemented analytics slices: `get_store_overview`, `get_revenue_metrics`, `get_order_metrics`, `get_product_performance`, `get_inventory_health`, `get_customer_metrics`, `get_sales_trends`, `get_merchant_health`, `get_opportunities`.
3. `commerce.read` is not a runtime permission. Propose-tool permissions (`recommendation.write`, `action.propose`) remain planned for Phase 6 and are not registered now.

ToolPort, allowlists, and tenant injection are unchanged: `ToolRegistry.for_agent` → strip model-supplied tenant fields → `TenantContext.from_session` / `from_job_row` → `AnalyticsService`.

## Alternatives

- Keep `commerce.read` for every read tool — rejected; violates least privilege
- Discover tools by importing callables — rejected; accidental exposure
- Let tool arguments supply `tenant_id` — rejected; contradicts ADR 0014

## Tradeoffs

Agents that need multiple slices must be granted multiple permissions. `AgentToolPort` derives permissions from the agent's allowlisted tools so a correctly bound agent is not under-authorized.

## Consequences

Update `docs/mcp.md`, `docs/contracts.md`, and `docs/agents.md`. Do not register mutation, SQL, HTTP, shell, or Shopify tools. Do not start LangGraph.
