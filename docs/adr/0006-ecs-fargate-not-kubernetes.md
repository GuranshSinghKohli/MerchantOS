# ADR 0006 — ECS Fargate, not Kubernetes

- **Status:** Accepted
- **Date:** 2026-08-25

## Context

The PRD specifies AWS ECS Fargate. Kubernetes would add cluster surface area without a V1 requirement.

## Decision

Run `api` and `worker` on ECS Fargate behind an ALB. Terraform manages the environment. Local `dev` uses Docker Compose.

## Alternatives

- EKS / Kubernetes — operationally heavier, not required
- Lambda-only — poor fit for long agent runs and persistent workers
- Always-on EC2 — more ops, worse scale-to-zero for a portfolio staging env

## Tradeoffs

Less portable off AWS. Acceptable: the PRD target is AWS.

## Consequences

No Helm, no service mesh. Scale workers on SQS depth. Do not introduce Kubernetes unless a concrete requirement appears.
