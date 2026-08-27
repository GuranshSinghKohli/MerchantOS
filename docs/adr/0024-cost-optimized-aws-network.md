# ADR 0024 — Cost-optimized AWS network (no NAT Gateway)

- **Status:** Accepted
- **Date:** 2026-08-26
- **Extends:** [0006](0006-ecs-fargate-not-kubernetes.md)
- **Does not supersede** 0006

## Context

Phase 10 deploys MerchantOS on AWS. The original target sketch put ECS tasks in private subnets and used a NAT Gateway for Shopify, LLM, ECR, SQS, and Secrets Manager egress.

A NAT Gateway is about $32/month before data-processing charges. Interface VPC endpoints for ECR, Secrets Manager, and SQS add more. That alone exceeds the student/demo cost target and does not buy a security property we cannot get another way.

RDS and Redis must stay unreachable from the internet. `/ready` still requires Redis, so ElastiCache is not optional without changing the application contract.

## Decision

- **No NAT Gateway.**
- **No interface VPC endpoints** in V1.
- ECS Fargate tasks (api, worker, web, migrate) run in **public subnets** with `assign_public_ip = true` so they can reach AWS APIs, Shopify, and the LLM provider through the internet gateway.
- RDS and ElastiCache stay in **private isolated subnets** with no internet route.
- The ALB is the only intended public ingress. Security groups allow 8000/3000 only from the ALB (plus ECS self on 8000 for Cloud Map).
- Redis remains required. It is private, TLS + auth token, not publicly addressed.
- Images are ARM64/Graviton (`256` CPU / `512` MiB, desired count 1).
- CloudWatch log retention is 7 days. Container Insights is off.
- Terraform remains the only IaC. Staging and production are separate state keys.
- CI deploys **immutable commit-SHA tags** to ECS. It does not apply Terraform with administrator credentials. First `terraform apply` is from a trusted operator after bootstrap.

HTTPS and Shopify OAuth against a production callback require a real domain + ACM certificate. Without a domain, the temporary URL is the ALB DNS name over HTTP, which is **not** valid for Shopify OAuth.

## Alternatives

- Private ECS + NAT — more isolation, ~$32+/month wasted for a demo
- Private ECS + interface endpoints — still expensive, more Terraform
- Skip Redis — would change `/ready` and rate-limit design
- Skip ALB / put one task on a public IP — weaker TLS and routing

## Tradeoffs

Tasks have public IPv4 addresses. Inbound is still security-group constrained. That is weaker than private-subnet + NAT, and it is the accepted cost/security tradeoff for V1. Public IPv4 (~$3.60/task/month) is cheaper than NAT.

Honest monthly floor for one always-on environment (ALB + 3 Fargate tasks + RDS t4g.micro + Redis t4g.micro) is about **$70–90**, not $20–40. Destroy staging when idle.

## Consequences

- Document the network in `docs/deployment.md`.
- Do not add a NAT Gateway “to match the old diagram” without a new ADR.
- Shopify URLs are updated only after an HTTPS origin exists.
- Operators set `public_base_url` (or `domain_name`) after the first apply so cookies and OAuth redirects are not `http://replace-with-alb-dns`.
