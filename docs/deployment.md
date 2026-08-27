# MerchantOS Deployment and Infrastructure

**Status:** Phase 10 accepted  
**Related:** [ADR 0006](adr/0006-ecs-fargate-not-kubernetes.md), [ADR 0010](adr/0010-sqs-async-workers.md), [ADR 0024](adr/0024-cost-optimized-aws-network.md)

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

`GET /health` does not require dependencies. `GET /ready` requires Postgres and Redis. Queue probe is `/ready/queue` and stays optional in dev.

Phase 2 OAuth/webhooks still need a public HTTPS tunnel when developing locally. `shopify.app.toml` `redirect_urls` must match exactly.

## AWS architecture

```
Internet
   ↓
ALB  (HTTP; HTTPS + redirect when domain_name is set)
  ↙ /api/* /health /ready     ↘ default
ECS api                        ECS web
   ↓
ECS worker  (no public listener)
   ↓
RDS (private)   Redis (private)   SQS + DLQ
Secrets Manager   CloudWatch
```

| Service | Why it exists |
|---------|----------------|
| ECR | Immutable API, worker, web images |
| ECS Fargate ARM64 | Independently scaled api / worker / web; migrate as RunTask |
| ALB | Path routing and (optional) TLS |
| RDS PostgreSQL 16 `db.t4g.micro` | Encrypted, private, 7-day backups |
| ElastiCache Redis 7 `cache.t4g.micro` | Required by `/ready` and rate limits; TLS + auth |
| SQS + DLQ | `{job_kind, job_id}` only; visibility 120s; maxReceiveCount 5 |
| Secrets Manager | DB, Redis, token DEK, Shopify, OpenAI |
| CloudWatch | 7-day logs + EMF metrics + four alarms |
| IAM | Separate execution / api / worker / GitHub OIDC roles |
| ACM | Only when `domain_name` is provided |

Not used in V1: NAT Gateway, interface VPC endpoints, Kubernetes, pgvector, CloudFront, Route 53 (unless you already have a zone), always-on S3 app bucket.

## Networking ([ADR 0024](adr/0024-cost-optimized-aws-network.md))

- Public subnets: ALB + ECS tasks with `assign_public_ip = true` (egress to Shopify, LLM, AWS APIs; no NAT)
- Private isolated subnets: RDS and Redis only; no internet route
- Security groups: ALB 80/443 from the internet; ECS 8000/3000 from the ALB; ECS self on 8000 for Cloud Map; 5432/6379 from ECS only
- RDS `publicly_accessible = false`; Redis has no public endpoint
- Worker has no load-balancer listener

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
5. First apply **without** services (creates ECR/RDS/Redis/SQS/ALB):

   `terraform apply -var='enable_services=false'`

6. Put Shopify / OpenAI values into Secrets Manager (`…/app`). Terraform ignores later `secret_string` drift so apply will not wipe operator keys.
7. Build and push ARM64 images tagged with a git SHA (never `latest` as the release id).
8. `terraform apply -var='enable_services=true' -var='image_tag=<sha>'`
9. Run migrate: `scripts/ecs-migrate.sh` (or CI).
10. Set `public_base_url` to `http://<alb_dns>` or set `domain_name` for HTTPS. Re-apply so `WEB_ORIGIN` / OAuth callback match.
11. Update Shopify app URLs **only after HTTPS is verified**.

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
| `REDIS_URL` (`rediss://`) | api, worker |
| `TOKEN_ENCRYPTION_KEY` | api, worker |
| `SHOPIFY_API_KEY` / `SHOPIFY_API_SECRET` | api, worker |
| `OPENAI_API_KEY` | worker only |

Frontend receives no server secrets. `API_UPSTREAM` is a container env for the Next rewrite at **image build** time; behind the ALB, `/api/*` is routed to the API service.

## IAM

- **Execution role:** pull images, write logs, `GetSecretValue` on the app secret (ECS injection).
- **API task role:** `sqs:SendMessage` / `GetQueueUrl` on the jobs queue only.
- **Worker task role:** receive/delete/change visibility on jobs + DLQ.
- **GitHub OIDC:** ECR push on `${name}/*`, ECS deploy/RunTask, `iam:PassRole` on the three task/execution roles. Main branch only. Not `AdministratorAccess`.

## CI/CD

Pull requests (`.github/workflows/ci.yml`): ruff, mypy, pytest, web lint/typecheck/vitest, `terraform fmt` + `validate`.

Main (`.github/workflows/deploy.yml`), only when `AWS_ROLE_ARN` is set:

1. Build `linux/arm64` images
2. Trivy (CRITICAL/HIGH fail)
3. Push `:sha`
4. Register new task definitions and update services
5. One-off migrate task (fail the deploy if it exits non-zero)
6. `scripts/smoke.sh` against `PUBLIC_URL` (`/health` + `/ready`)

Configure GitHub environment `staging` vars after the first apply: `AWS_ROLE_ARN`, `AWS_REGION`, `ECR_REGISTRY`, `ECR_PREFIX`, `ECS_CLUSTER`, `ECS_SUBNETS`, `ECS_SECURITY_GROUP`, `MIGRATE_TASK_FAMILY`, `PUBLIC_URL`.

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

If `domain_name` is set: ACM DNS validation, HTTPS listener, HTTP → HTTPS redirect. Cookie `Secure` is already on when `APP_ENV != dev`.

Without a domain: use the ALB DNS over HTTP and treat Shopify OAuth as **blocked**. Do not weaken OAuth to make HTTP work.

## Cost estimate (one always-on environment, us-east-1)

| Item | Approx. monthly |
|------|-----------------|
| ALB + low LCU | $16–22 |
| 3× Fargate ARM 0.25 vCPU / 0.5 GB | ~$27 |
| 3× public IPv4 on tasks | ~$11 |
| RDS `db.t4g.micro` + 20 GB gp3 | ~$13–15 |
| ElastiCache `cache.t4g.micro` | ~$12 |
| Secrets Manager + SQS + ECR + 7-day logs | ~$2–4 |
| **Total** | **~$70–90** |
| NAT Gateway (not deployed) | would add ~$32+ |

$20–40/month is not realistic while keeping ALB + RDS + Redis + three services. Save money by destroying staging when idle, not by skipping encryption or exposing the database.

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
