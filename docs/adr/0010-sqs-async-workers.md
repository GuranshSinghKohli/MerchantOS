# ADR 0010 — SQS for long-running work

- **Status:** Superseded by [0015](0015-transactional-outbox-and-leases.md)
- **Date:** 2026-08-25

## Context

Initial sync, agent graphs, and Shopify execution exceed request time budgets. Webhooks must ACK in under one second.

## Decision

API authenticates, persists a job/run row, and enqueues SQS. Workers process sync, agent runs, and executions. DLQs capture poison messages. Delivery is at-least-once; handlers are idempotent.

## Alternatives

- Inline FastAPI BackgroundTasks — die with the process, no DLQ
- Celery/Redis broker — extra moving part we do not need on AWS
- Step Functions for every run — heavier and costlier for V1

## Tradeoffs

Eventual consistency between enqueue and completion. Clients poll `/api/v1/ask/{run_id}`.

## Consequences

No LangGraph or Shopify mutation on the merchant request thread. Local `dev` uses Compose plus a later local queue stand-in.
