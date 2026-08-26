# Architecture Decision Records

ADRs record significant technical decisions for MerchantOS.

Template:

- **Status:** Proposed | Accepted | Superseded
- **Context:** why a decision is needed
- **Decision:** what we chose
- **Alternatives:** what we rejected
- **Tradeoffs:** cost of the choice
- **Consequences:** what implementers must do

Do not silently rewrite history. Supersede with a new ADR.

Index:

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-monorepo-and-service-layout.md) | Monorepo and service layout | Accepted |
| [0002](0002-graphql-admin-api.md) | Shopify GraphQL Admin API | Accepted |
| [0003](0003-standalone-oauth.md) | Standalone dashboard OAuth | Accepted (extended by 0017) |
| [0004](0004-mcp-in-process-registry.md) | In-process MCP tool registry | Accepted (isolation superseded by 0012) |
| [0005](0005-read-path-postgres.md) | Agent reads from Postgres | Accepted |
| [0006](0006-ecs-fargate-not-kubernetes.md) | ECS Fargate, not Kubernetes | Accepted |
| [0007](0007-approval-and-action-state-machines.md) | Separate approval and action machines | Superseded by 0013 |
| [0008](0008-llm-provider-port.md) | LLM provider port | Accepted |
| [0009](0009-server-injected-tenant-context.md) | Server-injected tenant context | Superseded by 0014 (async source) |
| [0010](0010-sqs-async-workers.md) | SQS for long-running work | Superseded by 0015 |
| [0011](0011-approval-gated-mutations.md) | Approval-gated Shopify mutations | Superseded by 0013 + 0016 |
| [0012](0012-capability-isolated-workers.md) | Capability-isolated workers | Accepted |
| [0013](0013-proposal-vs-approval-types.md) | Proposal vs approval types | Accepted |
| [0014](0014-tenant-from-job-row.md) | Tenant from job row only | Accepted |
| [0015](0015-transactional-outbox-and-leases.md) | Outbox and leases | Accepted |
| [0016](0016-deterministic-action-snapshots.md) | Deterministic action snapshots | Accepted |
| [0017](0017-oauth-and-mandatory-webhooks.md) | OAuth hardening and mandatory webhooks | Accepted |
