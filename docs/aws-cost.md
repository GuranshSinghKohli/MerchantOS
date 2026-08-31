# MerchantOS AWS cost estimate

**Not a bill.** us-east-1 list prices as of 2026-08, low traffic / portfolio demo, one always-on environment (staging **or** production, not both).

Architecture: [ADR 0025](adr/0025-portfolio-cost-envelope.md). No NAT Gateway. No ALB. No ElastiCache.

## Line items

| Service | Resource | Usage assumption | Est. / month |
|---------|----------|------------------|--------------|
| ECS Fargate | `edge` ARM `256` CPU / `512` MiB × 1, 730 h | Caddy + API + web | **$8–10** |
| Public IPv4 | 1 address on `edge` | $0.005/h | **$3.60–4** |
| ECS Fargate Spot | `worker` ARM `256` / `512` × 1 | ~70% off on-demand | **$2.50–4** |
| Public IPv4 | 1 address on `worker` (egress only) | required without NAT | **$3.60–4** |
| RDS | `db.t4g.micro` Postgres 16, single-AZ, 20 GB gp3, encrypted | 7-day backup | **$13–15** |
| SQS | jobs + DLQ | < 1M requests | **$0–0.20** |
| ECR | 4 repos, < 5 GB | scan on push | **$0.10–0.50** |
| Secrets Manager | 1 secret + low API volume | | **$0.40** |
| CloudWatch | 3 log groups, 7-day retention, 4 alarms | low volume | **$1–2** |
| SNS | email alerts | free tier / pennies | **$0–0.10** |
| NAT Gateway | not deployed | | **$0** |
| ALB | not deployed | | **$0** |
| ElastiCache | not deployed | | **$0** |
| CloudFront | not deployed | | **$0** |
| Route 53 | optional hosted zone for the A record | | **$0.50** if used |

## Estimated monthly total

**$33–40** for one environment at idle/low traffic. A Route 53 zone keeps the total in that band. An ALB does not ([ADR 0025](adr/0025-portfolio-cost-envelope.md)).

If Fargate Spot is unavailable, the worker falls back to on-demand and the total is about **$39–44**.

A **second** always-on environment (staging + production) roughly doubles this. Do not run both unless you accept ~$70–80.

## Assumptions

- One region (`us-east-1`)
- Desired count 1 for edge and worker
- FakeLLM (no OpenAI token spend)
- Shopify Admin traffic is small
- Log volume stays at INFO
- New-account free tier **not** assumed (RDS/ECS free tier is often already used or expired)

## What we refused to cut

- RDS encryption and 7-day backups
- Private database (no public RDS)
- Secrets Manager
- HTTPS when a domain is set (Let's Encrypt on Caddy)
- Separate worker task role / SQS least privilege
- DLQ + alarms

## Top 3 cost drivers

1. **RDS t4g.micro (~$14)** — smallest production Postgres. Stopping the instance when idle saves most of this; data remains if you do not delete the instance.
2. **Fargate + two public IPv4s (~$18–22)** — public IPs replace NAT (~$32). Combining worker into the edge task would save one IPv4 (~$3.60) and is the first lever if the bill exceeds $40.
3. **Worker on-demand fallback (~+$6)** — keep Spot; do not add an ALB to “look more production.”

## If the bill exceeds $40

| Lever | Saving | Tradeoff |
|-------|--------|----------|
| `terraform destroy` staging when idle | ~100% of staging | No public demo until re-apply |
| Stop (not delete) RDS overnight | ~half of RDS | `/ready` fails until started |
| Colocate worker on the edge task | ~$6–8 | Worker no longer scales alone |
| Turn desired count to 0 on worker | ~$6–8 | Jobs wait in SQS |

Do not drop backups, expose RDS, or skip Secrets Manager.

## Safe to stop/delete when unused

| Resource | Safe action |
|----------|-------------|
| Staging stack | `scripts/teardown-staging.sh` (`terraform destroy`) |
| ECS services | set `desired_count = 0` (RDS still bills) |
| RDS | **Stop** for up to 7 days (not delete) |
| Production | do not destroy from the staging script; disable `deletion_protection` first |

ECR images and the Terraform state bucket are cheap; keep them.
