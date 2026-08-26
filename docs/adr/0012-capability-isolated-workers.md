# ADR 0012 — Capability-isolated workers

- **Status:** Accepted
- **Date:** 2026-08-25
- **Supersedes:** [0004](0004-mcp-in-process-registry.md) *consequence that omitting `execute_approved_action` from the orchestrator list is sufficient isolation*. In-process MCP for **read/propose** tools remains.

## Context

Review C3: the graph and the executor share `apps/worker`. A “service account” was named but not designed. If the MCP registry contains a mutation tool, LangGraph can bind it.

## Decision

1. Delete `execute_approved_action` as a tool. It must not appear in any registry.
2. Split worker **handlers** and **capability objects**:
   - `AgentCapabilities` — ToolRegistry (allowlisted), LLMPort, run repo
   - `ExecutionCapabilities` — `ShopifyMutator`, action repo, audit
   - `SyncCapabilities` — `ShopifyReader` only
   - `WebhookCapabilities` — verifier + projection writer
3. `ShopifyMutator` and `ShopifyReader` are different interfaces.
4. Import-linter: `packages/agents` cannot import mutator, credentials, or `ApprovedAction`.

In-process MCP remains the V1 hosting choice for read/propose tools ([0004](0004-mcp-in-process-registry.md)).

## Alternatives

- Separate ECS services per job kind — more isolation, more cost; revisit if a handler leak is found
- Keep execute as a tool with a runtime flag — still visible to a mis-bound graph

## Tradeoffs

Two (or more) consumer loops in one repo. Clearer than one god worker.

## Consequences

See `docs/contracts.md` §5. Tests: agent handler cannot be constructed with execution capabilities; unknown execute tool name.
