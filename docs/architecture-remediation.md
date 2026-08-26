# Architecture review remediation

**Review date:** 2026-08-25  
**Original score:** 6.5/10 · 3 CRITICAL · 12 HIGH  
**Remediation date:** 2026-08-25  
**Canonical principles:** [`SYSTEM_DESIGN.md`](../SYSTEM_DESIGN.md)

| ID | Severity | Problem | Root Cause | Proposed Fix | Affected Files/ADRs | Status |
|----|----------|---------|------------|--------------|---------------------|--------|
| C1 | CRITICAL | LLM can author `approval_required`, `params`, `before`/`after` that later drive execution | Recommendation/action schemas treated model output as trusted HITL fields | `AgentActionProposal` has no approval/payload fields. `SnapshotService` builds before/after/payload from DB. `create_recommendation` drops `approval_required`. | `docs/contracts.md`, `docs/mcp.md`, `docs/agents.md`, `docs/security.md`, ADR 0013, ADR 0016 | Remediated |
| C2 | CRITICAL | Safety shares `LLMPort` and is modeled as an agent | One generic agent interface for every node | Safety is `PolicyService.evaluate` with no LLM. Graph calls it as a deterministic node. | `docs/contracts.md`, `docs/agents.md`, `SYSTEM_DESIGN.md` §23, ADR 0013 | Remediated |
| C3 | CRITICAL | `execute_approved_action` lives in the worker MCP registry; “service account” was undefined | Graph and executor share one process and one tool list | Tool is **deleted**. `ExecutionWorker` uses `ExecutionCapabilities` + `ApprovedAction.load`. Import-linter forbids agents from importing mutators. | `docs/contracts.md`, `docs/mcp.md`, `docs/architecture.md`, ADR 0012 | Remediated |
| H1 | HIGH | Graph only gated HIGH; MEDIUM also requires approval | Incomplete routing vs risk table | MEDIUM and HIGH → persist `PROPOSED` and `WAITING_APPROVAL`. CRITICAL → `BLOCKED`. No Shopify write without merchant `ApprovalRecord`. | `docs/agents.md`, `docs/security.md`, ADR 0013 | Remediated |
| H2 | HIGH | Per-agent tool lists were prose | Shared `ToolPort` with all tools | `AGENT_TOOLS` frozensets; `ToolPort.for_agent`; `ToolNotAllowed` at runtime | `docs/contracts.md`, `docs/mcp.md`, `docs/agents.md` | Remediated |
| H3 | HIGH | Worker could trust `merchant_id` on the SQS body | ADR 0009 allowed job payload as tenant source | Queue message is `{job_kind, job_id, traceparent}` only. `TenantContext.from_job_row`. | `docs/contracts.md`, `docs/architecture.md`, ADR 0014 (supersedes 0009) | Remediated |
| H4 | HIGH | No outbox; DB commit then SQS send can drop work | Principles §9 not modeled | `outbox_messages` table; same transaction as the business write; publisher to SQS | `docs/database.md`, `docs/deployment.md`, ADR 0015 (supersedes 0010) | Remediated |
| H5 | HIGH | No lease; duplicate graph runs; stuck `EXECUTING` | At-least-once without single-flight | CAS `PENDING→RUNNING` with `lease_until`; reaper; visibility timeout ≥ 2× max runtime | `docs/database.md`, `docs/architecture.md`, ADR 0015 | Remediated |
| H6 | HIGH | Payload frozen only after APPROVED; race while merchant views | Freeze point too late | Snapshot + `payload_hash` written at `PROPOSED`. Approval copies that hash. Executor requires match. | `docs/database.md`, `docs/contracts.md`, ADR 0013 | Remediated |
| H7 | HIGH | `validate_action` could return `allow` implying Shopify execute | Overloaded verdict | Verdict is only `require_approval` \| `block`. LOW internal writes are not ActionTypes. | `docs/mcp.md`, `docs/contracts.md`, `docs/security.md` | Remediated |
| H8 | HIGH | GDPR and `app/uninstalled` webhooks unspecified | Incomplete Shopify app contract | Mandatory topic catalog + handlers (uninstall revokes token/sessions) | `docs/architecture.md`, `docs/security.md`, `docs/deployment.md`, ADR 0017 | Remediated |
| H9 | HIGH | OAuth callback HMAC, revoke, reinstall unspecified | Standalone OAuth ADR stopped at grant type | Callback HMAC, shop match, redirect allowlist, uninstall revoke, reinstall upsert | `docs/security.md`, ADR 0017 (extends 0003) | Remediated |
| H10 | HIGH | Local SQS marked “later”; dev/prod async split | Compose omitted the queue | Compose includes ElasticMQ (or equivalent) from the first async phase; Phase 1 may still be sync-only health | `docs/deployment.md`, ADR 0015 | Remediated |
| H11 | HIGH | Private ECS subnets had no egress to Shopify/LLM | Diagram omitted NAT | NAT (or assigned public egress) required for api/worker; ACM, ECR documented | `docs/deployment.md` | Remediated |
| H12 | HIGH | AgentBench “production ToolPort” could hit real Shopify | Missing fake port | Production **tool code** + fixture DB + `FakeShopifyPort`; no prod credentials in eval | `docs/evaluation.md`, ADR 0008 remains, eval doc updated | Remediated |

## Second review (after remediation)

| | Before | After |
|--|--------|-------|
| Score | 6.5/10 | **9.0/10** |
| CRITICAL | 3 | **0** |
| HIGH | 12 | **0** |

Residual items are medium/low only (see closing report). Invariant is now expressed as types, factories, allowlists, and import rules in `docs/contracts.md`, not as prose on a tool list.
