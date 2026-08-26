# ADR 0015 — Transactional outbox and job leases

- **Status:** Accepted
- **Date:** 2026-08-25
- **Supersedes:** [0010](0010-sqs-async-workers.md) *“persist then enqueue” without an outbox, and local SQS deferred*. SQS as the bus remains.

## Context

Review H4, H5, H10: lost jobs if SQS send fails after COMMIT; duplicate graph runs; stuck EXECUTING; local queue marked later.

## Decision

1. `outbox_messages` is written in the **same transaction** as the job row (`agent_runs`, `sync_jobs`, `webhook_events` processed flag, `actions` queued).
2. A publisher relays unpublished outbox rows to SQS. Publish is at-least-once; consumers are idempotent on `job_id`.
3. Consumers take a lease: `UPDATE ... WHERE status=PENDING` (or equivalent) SET `RUNNING`, `lease_owner`, `lease_until`.
4. A reaper fails or requeues rows past `lease_until`.
5. SQS visibility timeout ≥ `2 * max_runtime` (agent 30s target → ≥ 60s; execution 15s + Shopify retry headroom → ≥ 60s).
6. `dev` Compose includes ElasticMQ (or LocalStack SQS) **before** the first async feature ships. Phase 1 (health only) does not need it.

## Alternatives

- Inbox only — does not fix produce-side loss
- Exactly-once SQS — not offered; we design for at-least-once

## Tradeoffs

Publisher process/loop. Standard and cheap.

## Consequences

Schema in `docs/database.md`. Tests: crash after COMMIT before publish still delivers; double delivery does not double-run a completed job.
