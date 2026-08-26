# ADR 0004 — In-process MCP tool registry

- **Status:** Accepted (hosting). Isolation consequence **superseded by** [0012](0012-capability-isolated-workers.md).
- **Date:** 2026-08-25

## Context

The PRD requires typed MCP tools. A separate MCP server process on every tool call adds latency and operations cost. Sidekick/MCP HTTP is P2.

## Decision

V1: in-process MCP-compatible registry in the worker (JSON Schema descriptors, typed I/O, authz, audit). Same descriptors can later be served over MCP HTTP without rewriting tools.

## Alternatives

- Always-on MCP subprocess — more “real MCP,” worse latency and failure modes for V1
- LangChain tools without schemas — weaker contracts and weaker AgentBench

## Tradeoffs

V1 is not a standalone MCP server. Portfolio narrative still shows MCP-shaped tools and a clean path to Sidekick.

## Consequences

`packages/mcp` has no LangGraph dependency. Mutation execution is **not a tool** ([0012](0012-capability-isolated-workers.md)). Do not implement the original “omit from orchestrator list” isolation.
