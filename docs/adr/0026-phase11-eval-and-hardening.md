# ADR 0026 — Phase 11 evaluation, security tests, and cost bounds

- **Status:** Accepted
- **Date:** 2026-08-31
- **Related:** [evaluation.md](../evaluation.md), [security.md](../security.md), [agents.md](../agents.md)

## Context

Phases 1–10 shipped the product loop through staging. Phase 11 must prove the system is measurable, tenant-isolated, injection-resistant, and bounded — without adding product features or applying production Terraform.

`docs/evaluation.md` previously targeted ≥ 250 scenarios and an `evaluation_runs` table. The repository already had a 17-scenario FakeLLM harness. Inventing a 250-row live-model scoreboard would contradict the “do not invent benchmark scores” rule and would call paid models in CI.

## Decision

- **CI AgentBench is FakeLLM-only.** Production agent/MCP/policy code is exercised; Shopify credentials and paid models are not.
- **Machine-readable results** are JSON under `artifacts/eval/`. `latest.json` is generated locally and gitignored. A checked-in `baseline.json` records the FakeLLM suite that CI must still pass. There is no `evaluation_runs` table in V1.
- **Scenario count is the real corpus size**, not a planning target. Core hand-authored cases plus generated injection/abuse/reliability families. Do not pad to 250.
- **Live-model AgentBench remains operator-gated** and is not required to merge.
- **Hardening is tests + small fail-closed fixes** (PII redaction on orchestrator LLM context, lease-recovery coverage, AWS contract tests). No new product surfaces, no execute tool, no pgvector, no Kubernetes.
- **Trivy stays report-only** on official Caddy/Next images we do not patch in-tree. Dependency upgrades are allowed only when compatibility is verified.
- **Production AWS apply remains operator-gated.**

## Alternatives

- Persist every eval row in Postgres — rejected for V1; JSON artifacts are enough to reproduce FakeLLM results
- Require 250 unique graph traces — rejected; generated families cover the attack classes without a fictionally large suite
- Fail CI on upstream image CVEs — rejected; those findings are in base images we do not own

## Tradeoffs

- FakeLLM measures policy, grounding, and isolation, not live-model quality
- Generated injection cases share specialist templates; they still run production tool authz

## Consequences

- Update `docs/evaluation.md` with methodology and the recorded baseline
- Do not treat a planning target of 250 as a verification number
- Do not start Phase 12 from this ADR
