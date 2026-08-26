# MerchantOS

AI-native commerce operating system for Shopify merchants.

Phase 1 is the engineering foundation only. There is no Shopify OAuth, no agents, no MCP tools, and no mock store analytics.

Canonical design: [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md). Architecture and Phase 1 closeout: [`docs/architecture.md`](docs/architecture.md#16-phase-1).

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
make worker   # idle connectivity loop (WORKER_ONCE=1 to exit after ping)
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
apps/worker       Idle worker (capability placeholder)
apps/web          Next.js App Router skeleton
packages/domain   TenantContext, QueueMessage, proposal types
packages/observability  JSON logs + redaction
packages/db       SQLAlchemy + Alembic (no domain tables yet)
packages/queue    QueuePort, InMemoryQueue, ElasticMqDevQueue (dev only)
infra/docker      Compose dependencies
```

## What is not here yet

Shopify credentials, LLM providers, MCP tools, commerce schema, Terraform/AWS, and merchant business logic. Those are later phases.
