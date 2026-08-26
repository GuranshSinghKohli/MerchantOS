# ADR 0008 — LLM provider port

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

Agents need a model. Coupling nodes to the OpenAI SDK blocks tests, cost routing, and evaluation comparisons.

## Decision

`packages/llm` exposes `LLMPort`. OpenAI is the first adapter. `FakeLLM` is used in CI and most AgentBench deterministic scenarios. Live-model eval is a separate lane.

## Alternatives

- Call OpenAI from each node — untestable and expensive CI
- Require live models on every PR — flaky and costly

## Tradeoffs

An extra interface. We gain determinism and provider independence.

## Consequences

`packages/agents` imports `LLMPort` only. Provider keys never enter domain or tool code. AgentBench versions the model id on each run.
