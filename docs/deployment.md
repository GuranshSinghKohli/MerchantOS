# MerchantOS Deployment and Infrastructure

**Status:** Phase 10 accepted  
**Related:** [ADR 0006](adr/0006-ecs-fargate-not-kubernetes.md), [ADR 0024](adr/0024-cost-optimized-aws-network.md), [ADR 0025](adr/0025-portfolio-cost-envelope.md), [staging HTTPS runbook](staging-https.md)

## Environments

| Name | Purpose | Data |
|------|---------|------|
| `dev` | Docker Compose on a laptop | Local Postgres/Redis; Shopify development store; `.env` |
| `staging` | AWS via Terraform | Isolated prefix; development store only; safe to destroy |
| `production` | AWS via Terraform | Never reused in dev/staging |

Credentials and merchant data never cross environments.

## Local (`dev`)

```
infra/docker/compose.yml
  postgres:16
  redis:7
  elasticmq (SQS-compatible)
apps/api          → localhost:8000
apps/worker       → sync / webhook / agent / execution
apps/web          → localhost:3000
```

Production-shaped images (non-root, multi-stage):

```
make image-build
docker compose -f infra/docker/compose.yml -f infra/docker/compose.images.yml up --build
```

`GET /health` does not require dependencies. `GET /ready` requires Postgres. Redis is required only when `REDIS_URL` is set (Compose/dev). Queue probe is `/ready/queue` and stays optional in dev.

Phase 2 OAuth/webhooks still need a public HTTPS tunnel when developing locally. `shopify.app.toml` `redirect_urls` must match exactly.

## AWS architecture

```
Route 53 A record (hostname)
   ↓
current edge task public IPv4  (changes when the task is replaced)
   ↓
Caddy :80/:443  (Let's Encrypt when domain_name is set)
  → API :8000 and web :3000 on localhost
ECS worker (Fargate Spot, no inbound)
   ↓
RDS (private)   SQS + DLQ
Secrets Manager   CloudWatch
```

The hostname is stable. The **task IP is not**. After every edge replace, update the A record ([staging-https.md](staging-https.md)). Do not front this with an ALB unless a new ADR replaces 0025.

| Service | Why it exists |
|---------|----------------|
| ECR | Immutable API, worker, web, Caddy images |
| ECS Fargate ARM64 | `edge` (Caddy+API+web) on-demand; `worker` on Spot; migrate as RunTask |
| Caddy | Public 80/443 and Let's Encrypt (no ALB) |
| RDS PostgreSQL 16 `db.t4g.micro` | Encrypted, private, 7-day backups |
| SQS + DLQ | `{job_kind, job_id}` only; visibility 120s; maxReceiveCount 5 |
| Secrets Manager | DB, token DEK, Shopify, OpenAI |
| CloudWatch | 7-day logs + EMF metrics + four alarms |
| IAM | Separate execution / api / worker / GitHub OIDC roles |

Not used in V1: NAT Gateway, ALB, ElastiCache, interface VPC endpoints, Kubernetes, pgvector, CloudFront, always-on S3 app bucket. Route 53 is optional DNS for the A record (~$0.50/month for a hosted zone). See [aws-cost.md](aws-cost.md).

## Networking ([ADR 0024](adr/0024-cost-optimized-aws-network.md))

- Public subnet: `edge` task (80/443) and `worker` (egress only), `assign_public_ip = true` (no NAT)
- Private isolated subnets: RDS only; no internet route
- Security groups: edge 80/443 from the internet; worker no inbound; RDS 5432 from edge+worker only
- RDS `publicly_accessible = false`
- No ElastiCache

## Terraform

IaC is Terraform only. Do not mix CDK or CloudFormation.

```
infra/terraform/
  bootstrap/          S3 state, DynamoDB lock, GitHub OIDC provider
  modules/            network ecr sqs rds redis secrets iam ecs observability
  envs/staging/
  envs/production/
```

### First apply (operator laptop)

1. Create an AWS account/region (`us-east-1` default).
2. `cd infra/terraform/bootstrap && terraform init && terraform apply -var bucket_name=<unique>`
3. Replace `merchantos-tfstate-replace-me` in the env backend blocks with that bucket.
4. `cd envs/staging && terraform init`
5. First apply **without** services (creates ECR/RDS/SQS, no ALB/Redis):

   `terraform apply -var='enable_services=false'`

6. Put Shopify / OpenAI values into Secrets Manager (`…/app`). Terraform ignores later `secret_string` drift so apply will not wipe operator keys.
7. Build and push ARM64 images tagged with a git SHA (never `latest` as the release id).
8. `terraform apply -var='enable_services=true' -var='image_tag=<sha>'`
9. Run migrate: `scripts/ecs-migrate.sh` (or CI).
10. Set `domain_name` and `public_base_url = "https://<hostname>"`. Apply, then follow [staging-https.md](staging-https.md) (new task IP → Route 53 A record → smoke HTTPS).
11. Update Shopify app URLs **only after HTTPS is verified**, and **only if the hostname changed**.

Production is the same layout with `deletion_protection = true`.

### Teardown

```
scripts/teardown-staging.sh
```

Do not destroy production from a script. Disable `deletion_protection` in a planned change first.

## Migrations

`python -m merchantos_db.migrate` (API image) creates `merchantos_app` (`NOSUPERUSER NOBYPASSRLS`) when `APP_DB_PASSWORD` is set, then `alembic upgrade head` as the RDS master URL.

- Never run from a request handler.
- Never auto-run destructive downgrades.
- Rollback is forward-only expand/contract. Restore from the 7-day RDS backup if a release is unsafe.

## Secrets

| Secret | Consumers |
|--------|-----------|
| `DATABASE_URL` (app role) | api, worker |
| `MASTER_DATABASE_URL` | migrate task only |
| `REDIS_URL` | local Compose only; unset in AWS |
| `TOKEN_ENCRYPTION_KEY` | api, worker |
| `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` | api, worker |
| `OPENAI_API_KEY` | worker only |

Frontend receives no server secrets. `API_UPSTREAM` is localhost for the Next server. Caddy routes `/api/*`, `/health`, and `/ready*` to the API container.

## IAM

- **Execution role:** pull images, write logs, `GetSecretValue` on the app secret (ECS injection).
- **API task role:** `sqs:SendMessage` / `GetQueueUrl` on the jobs queue only.
- **Worker task role:** receive/delete/change visibility on jobs + DLQ.
- **GitHub OIDC:** ECR push on `${name}/*`, ECS deploy/RunTask, `iam:PassRole` on the three task/execution roles. Main branch only. Not `AdministratorAccess`.

## CI/CD

Pull requests (`.github/workflows/ci.yml`): ruff, mypy, pytest, web lint/typecheck/vitest, `terraform fmt` + `validate`.

Main (`.github/workflows/deploy.yml`) deploys staging. Both jobs use `environment: staging`. GitHub OIDC `sub` for this repo is the immutable form `repo:<owner>@<id>/<repo>@<id>:environment:staging`. The IAM role must allow that subject. Do not gate jobs on environment `vars` in `if`.

1. Build `linux/arm64` images
2. Trivy (CRITICAL/HIGH fail)
3. Push `:sha`
4. Register new task definitions and update services
5. One-off migrate task (fail the deploy if it exits non-zero)
6. `scripts/smoke.sh` against `PUBLIC_URL` (`/health` + `/ready`)

Configure GitHub environment **`staging`** (Settings → Environments → `staging` → Environment variables), not repository secrets. Both deploy jobs read these vars. OIDC assumes `merchantos-staging-github` only for `main`.

| Variable | Staging value |
|----------|----------------|
| `AWS_ROLE_ARN` | `terraform output -raw github_role_arn` |
| `AWS_REGION` | `us-east-1` |
| `ECR_REGISTRY` | `<account>.dkr.ecr.us-east-1.amazonaws.com` |
| `ECR_PREFIX` | `merchantos-staging` |
| `ECS_CLUSTER` | `merchantos-staging` |
| `ECS_SUBNETS` | first public subnet from `terraform output -json public_subnet_ids` (no spaces) |
| `ECS_SECURITY_GROUP` | `terraform output -raw ecs_security_group_id` |
| `MIGRATE_TASK_FAMILY` | `merchantos-staging-migrate` |
| `PUBLIC_URL` | `https://merchantos.duckdns.org` |

After a CI deploy the edge IP changes. Update DuckDNS, then re-run smoke (`docs/staging-https.md`). A first `workflow_dispatch` is enough to test; do not apply production.

## Observability and alerts

Logs: `/merchantos/<env>/{api,worker,web,migrate}`, 7-day retention.

Application EMF (`AWS_EMF_NAMESPACE`): API request count/latency/4xx/5xx; worker completed/retry/failed.

Alarms (SNS email when `alarm_email` is set):

- API target 5xx > 5 / 5 min
- Unhealthy API hosts > 0
- SQS oldest message age > 300s
- DLQ visible messages > 0

Never log access tokens, passwords, API keys, or full sensitive payloads.

## Domain / TLS / Shopify

Operator procedure: [staging-https.md](staging-https.md).

If `domain_name` is set: Caddy requests a Let's Encrypt certificate. Point a Route 53 **A** record at the current edge public IP (`scripts/edge-public-ip.sh`). The IP changes on replace; the hostname does not. Cookie `Secure` is already on when `APP_ENV != dev`.

Without a domain: HTTP on the task public IP. Treat Shopify OAuth as **blocked**. Do not weaken OAuth to make HTTP work. Do not add Cloudflare or an ALB to work around this.

## Cost estimate (one always-on environment, us-east-1)

See [aws-cost.md](aws-cost.md). **~$33–40/month**. No ALB, no NAT, no ElastiCache. Destroy staging when idle.

## Rollback

1. `aws ecs update-service --task-definition <previous-revision>`
2. Confirm `/health` and `/ready`
3. Do not `alembic downgrade` in production
4. If data is wrong, restore RDS from automated backup
5. Actions are not silently undone; record a compensating action

## Performance targets (from PRD)

| Area | Target |
|------|--------|
| Dashboard API p95 | < 500 ms (excluding long analytics) |
| Standard analytics p95 | < 5 s |
| Typical agent workflow | < 30 s |
| Action enqueue | < 2 s |
| Webhook ACK | < 1 s |
| V1 availability | 99.5% excluding planned maintenance |
