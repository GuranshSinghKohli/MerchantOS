# ADR 0025 — Portfolio cost envelope (no ALB, no ElastiCache)

- **Status:** Accepted
- **Date:** 2026-08-29
- **Extends:** [0006](0006-ecs-fargate-not-kubernetes.md), [0024](0024-cost-optimized-aws-network.md)
- **Supersedes (in part):** ADR 0024 decisions that ElastiCache and an ALB are required for V1 AWS

## Context

ADR 0024 kept an ALB and ElastiCache. Honest always-on cost was **$70–90/month**. The portfolio target is **~$30–40/month** without dropping encryption, Secrets Manager, RDS backups, HTTPS, or tenant isolation.

Cost audit of the previous stack:

| Item | Why expensive |
|------|----------------|
| ALB | ~$16–22/month idle |
| ElastiCache `cache.t4g.micro` | ~$12/month |
| Third Fargate task + public IPv4 | ~$13/month |
| NAT Gateway | already rejected (~$32+) |

Application audit: Redis is **not** used for sessions, cache, or the queue. [ADR 0020](0020-analytics-on-read.md) computes analytics on read with no Redis cache. Redis was only pinged by `/ready` and worker startup. Compose/dev still runs Redis.

ACM on an ALB is the usual AWS TLS path. That ALB fee alone consumes half the budget.

## Decision

- **Do not deploy ElastiCache.** Production `/ready` requires Postgres only. Redis is reported as `"skipped"` when `REDIS_URL` is unset. Dev/CI keep Compose Redis and still require it when `REDIS_URL` is set.
- **Do not deploy an ALB or NAT Gateway.**
- Public entry is **Caddy on the `edge` Fargate task** (ports 80/443). Caddy reverse-proxies `/api/*`, `/health`, and `/ready*` to the API container and everything else to the web container on `localhost` (awsvpc).
- HTTPS uses **Caddy + Let's Encrypt** when `domain_name` is set. ACM+ALB is the rejected alternative because of cost. Without a domain, HTTP on the task public IP is temporary and **not** valid for Shopify OAuth.
- **Worker is a separate service** on **Fargate Spot** (256/512). Jobs are idempotent; interruption is a retry, not data loss. Edge stays on-demand.
- RDS remains `db.t4g.micro`, single-AZ, encrypted, private, 7-day backups. Two private subnets exist only because RDS subnet groups require two AZs.
- CloudWatch log retention stays 7 days. Container Insights stays off.

## Alternatives

- Keep ALB + Redis — misses the cost target
- Public RDS — rejected (security)
- Skip RDS backups — rejected
- One combined api+worker task — cheaper, but worker could not scale independently
- CloudFront + public IP origin — HTTPS hostname is stable, but the task IP changes on every deploy

## Tradeoffs

- No multi-AZ ALB failover. One edge task. Documented for a portfolio demo.
- Let's Encrypt needs a DNS A record aimed at the current task public IP after each replace.
- Fargate Spot may interrupt the worker; SQS visibility + idempotency cover that.
- `/ready` in AWS does not prove Redis. Dev still does.

## Consequences

- Estimated always-on staging/production: **~$33–40/month** ([docs/aws-cost.md](../aws-cost.md)).
- Do not add an ALB or ElastiCache “to match the old diagram” without a new ADR and a cost update.
- Update Shopify URLs only after HTTPS on the domain works, and only if the hostname changes. After each edge replace, update the Route 53 A record ([staging-https.md](../staging-https.md)).
