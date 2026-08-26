# MerchantOS Deployment and Infrastructure

**Status:** Accepted for V1 planning  
**Related:** [ADR 0006](adr/0006-ecs-fargate-not-kubernetes.md), [ADR 0010](adr/0010-sqs-async-workers.md)

## Environments

| Name | Purpose | Data |
|------|---------|------|
| `dev` | Docker Compose on a laptop | Local Postgres/Redis; Shopify development store; `.env` |
| `staging` | AWS via Terraform | Isolated account or prefix; development store only |
| `production` | AWS via Terraform | Never reused in dev/staging |

Credentials and merchant data never cross environments.

## Local (`dev`)

```
infra/docker/compose.yml
  postgres:16
  redis:7
  elasticmq (SQS-compatible) — required before the first async feature
apps/api          → localhost
apps/worker       → agent / execution / sync / webhook handlers (separate capabilities)
apps/web          → localhost (from Overview phase)
```

Phase 1 (health/ready only) does not start workers or the queue. OAuth/webhook phases require a documented HTTPS tunnel (ngrok or Cloudflare Tunnel).

`GET /health` does not require dependencies. `GET /ready` requires Postgres and Redis.

## AWS target

```
                    ┌─ CloudWatch + OTel ─┐
Shopify ──OAuth/WH──┤                      │
                    ▼                      │
                   ALB                     │
                    │                      │
            ECS Fargate api                │
                    │                      │
         ┌──────────┼──────────┐           │
         ▼          ▼          ▼           │
        RDS      Redis        SQS+DLQ      │
     Postgres   ElastiCache      │         │
         ▲                       ▼         │
         └──────── ECS Fargate worker ─────┘
                            │
                     S3  Secrets Manager
```

| Service | Use |
|---------|-----|
| ALB | TLS termination, path routing to api |
| ECS Fargate | `api` and `worker` services, independently scaled |
| RDS PostgreSQL | Primary state |
| ElastiCache Redis | Rate limits, short cache, optional session store |
| SQS + DLQ | Sync, webhooks, agent runs, action execution |
| S3 | Eval fixtures, traces, artifacts |
| Secrets Manager | Shopify, DB, LLM, session keys |
| CloudWatch + ADOT/OTel | Logs, metrics, traces |
| IAM | Separate task roles for api vs worker |

No Kubernetes in V1. No production resources created only in the AWS console.

## Networking

- Public: ALB only (ACM certificate)
- Private subnets: ECS tasks, RDS, Redis
- **NAT gateway (or equivalent egress)** so api/worker can reach Shopify GraphQL and the LLM provider
- Security groups: api → RDS/Redis/SQS/Secrets/NAT; worker → same; no inbound to worker from internet
- RDS and Redis not publicly reachable
- Images in ECR; tasks pull via VPC endpoints or NAT

## IAM least privilege (sketch)

**api task role:** `sqs:SendMessage` on app queues (or only if not using DB outbox publisher on api), `secretsmanager:GetSecretValue` on api secrets, `s3:PutObject` if needed for traces.

**worker task role:** `sqs:ReceiveMessage/DeleteMessage` on app queues, `secretsmanager:GetSecretValue` on worker secrets, `s3:GetObject/PutObject` on artifact bucket.

Shopify tokens are app secrets, not IAM. The agent handler never receives `ShopifyMutator`. Prefer separate worker **task definitions** (agent vs execution) when it is cheap; until then, separate capability factories in-process ([ADR 0012](adr/0012-capability-isolated-workers.md)). Compensating control if one task definition: import-linter + constructor types. Revisit split services if a leak is found.

Neither role has `*:*`. Neither role needs Shopify credentials in IAM — those are app secrets.

## Terraform layout

```
infra/terraform/
  modules/
    network/
    ecs/
    rds/
    redis/
    sqs/
    s3/
    iam/
    observability/
  envs/
    staging/
    production/
```

State in a remote backend (S3 + lock). Workspaces or separate state per env.

## CI/CD

Every pull request:

1. Format (ruff / prettier)
2. Lint
3. Typecheck (mypy, tsc when web exists)
4. Unit tests
5. Relevant integration tests (Compose services)
6. Security scan

Production deploy:

1. CI green
2. Container build
3. Image scan
4. Staging apply + migrate + smoke (`/health`, `/ready`)
5. Production apply + migrate + smoke

Never deploy production from a laptop. Never skip hooks unless the human explicitly requests it.

Migrations run as a one-off ECS task or CI step against the env database, never as a side effect of request handling.

## Performance targets (from PRD)

| Area | Target |
|------|--------|
| Dashboard API p95 | < 500 ms (excluding long analytics) |
| Standard analytics p95 | < 5 s |
| Typical agent workflow | < 30 s |
| Action enqueue | < 2 s |
| Webhook ACK | < 1 s |
| V1 availability | 99.5% excluding planned maintenance |

## Cost awareness

Track LLM tokens/cost per run, RDS, Fargate, Redis, SQS, S3, egress. Prefer one region. Scale workers on queue depth, not always-on large tasks. Do not add clusters or meshes without a requirement.

## Rollback

- ECS: previous task definition
- Terraform: plan/apply reverse or prior tag
- DB: forward-only; expand/contract migrations, no untested down on prod
- Actions: compensating action recorded on the approval, not silent undo
