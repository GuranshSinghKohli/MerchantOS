# MerchantOS

AI-native commerce operating system for Shopify merchants.

Phase 9 adds merchant-approved, allowlisted Shopify product mutations. The model may propose; only an authenticated merchant can approve; a deterministic worker executes.

Canonical design: [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md). Architecture: [`docs/architecture.md`](docs/architecture.md).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 and [pnpm](https://pnpm.io) 9
- Docker Desktop **running**. The `docker` CLI and Compose plugin must be on PATH (Postgres 16, Redis 7, ElasticMQ).

## Local setup

```bash
cp .env.example .env
make deps
make up
make migrate
```

Run the three processes in separate terminals:

```bash
make api      # http://localhost:8000/health  /ready
make worker   # sync + webhook consumer (WORKER_ONCE=1 drains one batch and exits)
make web      # http://localhost:3000
```

`GET /health` does not require dependencies. `GET /ready` requires Postgres and Redis.

If `docker` is missing after installing Docker Desktop on macOS, prepend the app CLI **before** `make up`. A new shell does not keep this unless you add it to your profile:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

If `docker compose` is still unknown, expose Desktop’s Compose plugin:

```bash
mkdir -p ~/.docker/cli-plugins
ln -sf /Applications/Docker.app/Contents/Resources/cli-plugins/docker-compose ~/.docker/cli-plugins/docker-compose
```

Integration tests run whenever `DATABASE_URL` is set (including via `.env`). They fail if Compose is down; they do not skip.

## Quality

```bash
make lint
make typecheck
make test
```

## Layout

```
apps/api          FastAPI
apps/worker       Sync + webhook + agent + execution workers
apps/web          Next.js dashboard
packages/domain   TenantContext, QueueMessage, proposal types
packages/app      Analytics, policy, approval services
packages/mcp      In-process read-tool registry (no execute tools)
packages/llm      LLMPort, FakeLLM, OpenAI adapter
packages/agents   LangGraph orchestrator (no ApprovedAction / mutator)
apps/agentbench   Deterministic runtime evaluation harness
packages/observability  JSON logs, redaction, CloudWatch EMF
packages/db       SQLAlchemy + Alembic + migrate CLI
packages/shopify  OAuth, HMAC, GraphQL Admin 2026-07, typed mutator
packages/queue    QueuePort, InMemory, ElasticMQ (dev), AwsSqsQueue (AWS)
infra/docker      Compose dependencies + production image smoke
infra/terraform   Staging/production AWS (ECR, ECS, RDS, Redis, SQS)
```

## Shopify install (Phase 2)

1. Create a Shopify Dev Dashboard / Partner app (standalone, not embedded).
2. Copy client id/secret into `.env` (`SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`).
3. Generate `TOKEN_ENCRYPTION_KEY` (32-byte urlsafe base64).
4. Set `SHOPIFY_REDIRECT_URI` to an allowlisted HTTPS callback (local: a tunnel such as ngrok or Cloudflare Tunnel, then `/api/v1/auth/shopify/callback`).
5. Put the same callback in `shopify.app.toml` `[auth].redirect_urls` and in the Dev Dashboard.
6. Open `http://localhost:3000/install` and enter `{store}.myshopify.com`.

The browser never receives the offline access token. `GET /api/v1/me` returns shop + scopes only.

Metric definitions: [`docs/metrics.md`](docs/metrics.md). Dashboard visual system: [`docs/DESIGN.md`](docs/DESIGN.md).

## AWS (Phase 10)

Terraform lives in `infra/terraform/`. See [`docs/deployment.md`](docs/deployment.md) and [ADR 0024](docs/adr/0024-cost-optimized-aws-network.md).

Live apply needs an AWS account, a unique state bucket, and (for Shopify OAuth) an HTTPS domain. This repository does not contain AWS credentials.

```
make image-build
make tf-validate
```

## What is not here yet

MCP HTTP, Sidekick, token refresh, and later product phases. Do not start Phase 11 from the README.
