# MerchantOS — System Design Principles

This is the **canonical** engineering source for MerchantOS. Cursor rules, ADRs, and `docs/*` must not contradict it. If they disagree, this file wins until a new ADR supersedes a decision and this file is updated.

---

## 1. Purpose

MerchantOS is a production-grade AI-native commerce operating system built on top of Shopify.

The system must demonstrate:

- Strong software engineering
- Distributed systems design
- Agentic AI engineering
- Cloud architecture
- Security
- Observability
- Reliability
- Product thinking

The objective is NOT to maximize the number of technologies used.

The objective is to build the smallest architecture that can reliably support the product requirements.

---

## 2. Core Architectural Principle

MerchantOS follows:

OBSERVE
→ UNDERSTAND
→ DIAGNOSE
→ PLAN
→ RECOMMEND
→ APPROVE
→ EXECUTE
→ MEASURE

AI is responsible for reasoning.

Deterministic application services are responsible for authorization, validation, execution, persistence, and security.

NEVER allow an LLM to bypass deterministic application controls.

---

## 3. Separation of Concerns

The system must have clear boundaries between:

Frontend
API
Domain
Data
Agents
Tools
External integrations
Infrastructure

Preferred dependency direction:

Frontend
↓
API
↓
Application Services
↓
Domain
↓
Repositories / Infrastructure

Agents should interact with application capabilities through typed interfaces/tools.

External services should never leak directly into business logic.

---

## 4. AI Is NOT the Authority

LLMs must NEVER be treated as trusted components.

The LLM can:

- Interpret user intent
- Generate plans
- Select tools
- Analyze retrieved information
- Generate recommendations
- Propose actions and rationale

The LLM cannot independently:

- Authorize itself
- Change permissions
- Access another tenant
- Execute arbitrary API calls
- Construct unrestricted Shopify requests
- Bypass approval
- Create or modify an approval
- Manufacture an approved action
- Modify security policies
- Access secrets

All of those operations must be controlled deterministically. See `docs/contracts.md`.

---

## 5. Tool-First Agent Architecture

Agents interact with the world through typed tools.

Never provide an agent with unrestricted access to:

- HTTP clients
- Database connections
- Shopify credentials
- AWS credentials
- Arbitrary shell commands
- Mutation / execute tools

Instead:

Agent
↓
Typed Tool
↓
Authorization
↓
Validation
↓
Service
↓
External System

Every tool must define:

- Input schema
- Output schema
- Permissions
- Tenant scope
- Risk level
- Timeout
- Retry behavior
- Audit requirements

---

## 6. Multi-Tenancy

MerchantOS is multi-tenant by design.

Every merchant-owned entity must have a tenant/store relationship.

Examples:

merchant_id
store_id

Every database query involving merchant data must enforce tenant isolation.

Never rely on the LLM to provide the correct tenant.

Tenant context must come from authenticated server-side context.

Bad:

agent → database → query using tenant_id supplied by LLM

Good:

authenticated request
↓
server establishes tenant context
↓
job row stores merchant_id
↓
worker loads TenantContext from that row
↓
agent/tool receives trusted tenant context
↓
repository enforces tenant boundary

Never accept tenant identity from:

- LLM output
- user-provided tool arguments
- arbitrary agent state
- SQS/queue message bodies

Tenant isolation must exist at:

- API
- Service
- Repository
- Tool
- Database

layers.

---

## 7. Shopify Integration Boundary

Shopify integration must be isolated behind a dedicated integration layer.

Business logic should NOT directly depend on Shopify SDK/API implementation details.

Preferred:

Application Service
↓
ShopifyService Interface
↓
Shopify Adapter
↓
Shopify API

This makes Shopify:

- Testable
- Replaceable
- Mockable
- Versionable

The system must handle:

- OAuth
- API versioning
- Rate limits
- Pagination
- Webhooks
- Retries
- Idempotency
- External API failures
- Uninstall and token revocation
- Mandatory compliance webhooks

---

## 8. Database Principles

PostgreSQL is the primary source of normalized application state.

Use:

- Explicit schemas
- Foreign keys
- Constraints
- Proper indexes
- Transactions
- Migrations
- Connection pooling

Avoid:

- Unstructured JSON everywhere
- Duplicate sources of truth
- Business logic hidden inside SQL
- Missing constraints
- N+1 queries

JSON/JSONB may be used where appropriate for:

- Agent metadata
- Tool metadata
- External payload fragments
- Evaluation configuration

but core relational entities should remain strongly modeled.

---

## 9. Transaction Boundaries

Use database transactions for operations that must be atomic.

Example:

Creating an approved action should not result in:

Approval saved
but
Action missing

or:

Action executed
but
Audit record missing

Where true distributed transactions are impossible, use:

- Idempotency
- State machines
- Outbox patterns
- Compensating actions

rather than assuming atomicity across external systems.

---

## 10. Idempotency

Any operation that may be retried must be idempotent.

Especially:

- Shopify webhooks
- Data synchronization
- Action execution
- Queue processing
- Agent-triggered mutations (which must still go through approval)

Use explicit idempotency keys.

Example:

request_id
event_id
action_id
job_id

Never assume an external request is executed exactly once.

Design for:

AT LEAST ONCE DELIVERY.

---

## 11. Asynchronous Architecture

Long-running operations must NOT block synchronous API requests.

Examples:

- Initial Shopify synchronization
- Large data imports
- Agent workflows
- Evaluation runs
- Bulk operations
- Scheduled analysis

Preferred architecture:

API
↓
DB row + outbox (same transaction)
↓
SQS
↓
Worker with a job-specific capability set
↓
Processing
↓
Database / external API

The API should return a job/run identifier when appropriate.

Queue messages carry job identifiers only, never tenant ids or secrets.

---

## 12. State Machines

Important workflows should use explicit state transitions.

Examples:

AgentRun:

PENDING
→ RUNNING
→ COMPLETED

or:

PENDING
→ RUNNING
→ FAILED

or:

PENDING
→ RUNNING
→ WAITING_APPROVAL
→ COMPLETED

Approval:

exists only after an authenticated merchant decision

PENDING is not created by agents.

Merchant approve → APPROVED
Merchant reject → REJECTED
Expiry job → EXPIRED

Action:

PROPOSED
→ APPROVED
→ QUEUED
→ EXECUTING
→ COMPLETED

or:

PROPOSED
→ BLOCKED

or:

EXECUTING
→ FAILED

Do not represent important workflow state through ambiguous booleans.

Avoid:

is_running
is_finished
has_error
is_approved

when a proper state machine is more appropriate.

---

## 13. Human-in-the-Loop Safety

All meaningful Shopify mutations must pass through:

Agent Proposal
↓
Deterministic Policy
↓
Merchant Approval (authenticated session)
↓
Execution Queue
↓
Execution Worker
↓
Shopify Adapter
↓
Audit

The agent cannot approve its own action.

The agent cannot create or modify an approval.

The frontend cannot directly execute Shopify mutations.

Only the execution worker, given an `ApprovedAction` loaded from the database, can execute approved actions.

---

## 14. Risk Classification

Every action has a risk level.

LOW
MEDIUM
HIGH
CRITICAL

Risk classification must be deterministic where possible.

Do not rely solely on an LLM to determine whether its own action is safe.

Example:

Changing product title:
LOW/MEDIUM

Changing price:
HIGH

Changing hundreds of prices:
CRITICAL

Deleting products:
CRITICAL

MEDIUM and HIGH Shopify mutations require merchant approval.

Critical operations should be blocked in V1.

LOW means internal/non-mutating only. LOW never calls Shopify write APIs.

---

## 15. Security by Design

Security is not a final phase.

Security must exist from the beginning.

Requirements:

- No secrets in source control
- No secrets in logs
- Secrets Manager for production secrets
- Least privilege IAM
- Least privilege Shopify scopes
- Input validation
- Output validation
- Authentication
- Authorization
- Rate limiting
- Tenant isolation
- Secure cookies/tokens
- Dependency scanning
- Container scanning

---

## 16. Prompt Injection Defense

Merchant data is untrusted.

Product descriptions
Customer notes
Reviews
Order metadata
Imported text

may contain malicious instructions.

Never allow retrieved text to redefine:

- Agent instructions
- Tool permissions
- Tenant identity
- Security policy
- Approval requirements

Treat external content strictly as DATA.

System instructions and authorization logic must remain higher priority.

---

## 17. Secrets

Secrets must NEVER appear in:

- Source code
- Git
- Logs
- Agent context
- Database records unless encrypted for a specific reason
- Frontend bundles

Production secrets:

AWS Secrets Manager

Local development:

.env files excluded from Git

Agents should never receive raw Shopify credentials.

---

## 18. Observability

Every important operation must be observable.

Track:

- Request ID
- Trace ID
- AgentRun ID
- ToolCall ID
- Action ID

Metrics should include:

- Request latency
- Agent latency
- Tool latency
- Queue depth
- Queue failures
- Shopify API errors
- Agent failures
- Token usage
- Estimated cost
- Action success rate
- Evaluation scores

A production issue should be diagnosable without reproducing it locally.

---

## 19. Structured Logging

Use structured logs.

Prefer:

{
  "event": "shopify_action_completed",
  "action_id": "...",
  "store_id": "...",
  "duration_ms": 1234,
  "status": "success"
}

over:

"Action completed successfully!"

Never log:

- Access tokens
- Passwords
- API keys
- Full customer PII unnecessarily
- Secrets

---

## 20. Error Handling

Never silently swallow errors.

Every error must either:

- Be handled
- Be returned
- Be retried
- Be recorded
- Cause a controlled failure

Use typed/domain errors where appropriate.

Differentiate:

- Validation errors
- Authentication errors
- Authorization errors
- External API errors
- Rate-limit errors
- Database errors
- Agent errors
- Configuration errors

Do not return raw internal stack traces to users.

---

## 21. Retry Strategy

Retries must be deliberate.

Retry:

- transient network failures
- temporary Shopify failures
- temporary database failures
- rate limits

Do not blindly retry:

- validation failures
- authorization failures
- malformed requests
- permanent business errors

Use:

- exponential backoff
- jitter
- maximum attempts
- dead-letter queues

---

## 22. API Design

APIs should be:

- RESTful where appropriate
- Versioned
- Typed
- Validated
- Documented

Example:

/api/v1/stores
/api/v1/insights
/api/v1/agent-runs
/api/v1/recommendations
/api/v1/approvals
/api/v1/actions

Avoid exposing internal implementation details.

---

## 23. Agent Design

Agents should be:

- Small
- Specialized
- Testable
- Observable
- Replaceable

Avoid creating one enormous "super agent."

Each agent should have:

Purpose
Input
State
Tools
Output
Failure modes

The orchestrator coordinates agents.

Safety / policy is not an agent. It is a deterministic application service.

---

## 24. Agent State

Agent state should contain only information necessary for the workflow.

Example:

{
  request_id,
  tenant,          # trusted TenantContext, not model-writable
  user_intent,
  plan,
  evidence,
  tool_results,
  findings,
  recommendations,
  proposed_actions
}

Avoid passing unnecessary merchant data through every agent.

Minimize context size.

Agent state must not contain:

- approval records
- approved actions
- Shopify tokens
- a writable tenant_id

---

## 25. LLM Provider Abstraction

Do not tightly couple business logic to one model provider.

Preferred:

LLM Interface
↓
Provider Adapter
↓
OpenAI / Other Provider

This allows:

- Model upgrades
- Testing
- Cost optimization
- Fallback models
- Evaluation comparisons

---

## 26. Deterministic vs Probabilistic Logic

Use LLMs for:

- Reasoning
- Classification
- Summarization
- Strategy generation

Use deterministic code for:

- Authorization
- Permissions
- Risk limits
- Financial calculations
- Validation
- State transitions
- Database writes
- Shopify mutations
- Security decisions

This distinction is mandatory.

---

## 27. Financial / Business Calculations

Never rely on an LLM for exact financial calculations.

Use deterministic application code for:

- Revenue
- Profit
- Margin
- AOV
- Percent changes
- Inventory quantities
- Forecast calculations

The LLM can explain the result but should not be the calculator of record.

---

## 28. Testing Pyramid

Use:

Many unit tests
↓
Integration tests
↓
End-to-end tests
↓
Agent evaluation tests

Agent tests must not require live model calls for every CI run.

Use deterministic fixtures and mocked model responses for normal CI.

Use live-model evaluation separately.

---

## 29. AgentBench Principles

AgentBench must measure real behavior.

Never optimize prompts purely to make benchmark numbers look good.

Track:

- Task success
- Tool selection
- Tool arguments
- Groundedness
- Safety
- Latency
- Cost
- Robustness

Evaluation datasets must be version controlled.

AgentBench uses production tool code, fixture data, FakeLLM (CI), and FakeShopifyPort. It never receives production Shopify credentials.

---

## 30. CI/CD

Every pull request should run:

- Formatting
- Lint
- Type checking
- Unit tests
- Relevant integration tests
- Security checks

Production deployment should require:

- Passing CI
- Successful build
- Staging deployment
- Smoke tests

Never deploy directly from a developer laptop.

---

## 31. Infrastructure as Code

AWS infrastructure must be reproducible.

Use Terraform.

Do not mix CDK or CloudFormation.

Do not manually create production infrastructure unless documented and later codified.

V1 network: no NAT Gateway; ECS tasks use public subnets and public IPs; RDS and Redis stay private ([ADR 0024](docs/adr/0024-cost-optimized-aws-network.md)).

Infrastructure should be separated by environment:

dev
staging
production

---

## 32. Cost Awareness

Every infrastructure and AI decision should consider cost.

Track:

- LLM cost
- Database usage
- ECS compute
- Redis
- SQS
- S3
- Network usage

Avoid unnecessarily expensive architecture.

Do not introduce Kubernetes unless there is a genuine requirement.

ECS Fargate is preferred for V1.

---

## 33. Scalability

Design for horizontal scaling.

Stateless API services should be horizontally scalable.

Workers should scale independently.

Database access should use pooling.

Long-running work should be asynchronous.

Do not optimize prematurely.

Build for reasonable scale first.

---

## 34. Dependency Discipline

Before adding a dependency ask:

1. Is it necessary?
2. Is there already an existing solution?
3. Is it maintained?
4. Does it introduce security risk?
5. Does it significantly increase complexity?

Avoid dependency sprawl.

---

## 35. Code Organization

Prefer:

feature-oriented organization

over:

massive generic utility folders.

Avoid:

utils/
helpers/
misc/

becoming dumping grounds.

Business logic should have a clear home.

Application services live in `packages/app` (or `apps/*/services` calling `packages/app`). They are the only layer that coordinates domain + repositories + ports.

---

## 36. Documentation

Important architectural decisions should be documented.

Maintain:

docs/
  architecture.md
  security.md
  agents.md
  mcp.md
  database.md
  deployment.md
  evaluation.md
  contracts.md
  architecture-remediation.md
  adr/

Use ADRs for meaningful architectural decisions.

This file (`SYSTEM_DESIGN.md`) is the canonical principle set.

---

## 37. Architecture Decision Records

When making a significant decision, document:

Context
Decision
Alternatives
Tradeoffs
Consequences

Do not silently rewrite accepted ADRs. Supersede them with a new ADR.

---

## 38. Git Principles

Use small, meaningful commits.

Example:

feat(shopify): add OAuth installation flow

feat(sync): add product synchronization worker

feat(mcp): add product metrics tool

feat(agent): add analytics agent

test(agent): add analytics evaluation scenarios

Avoid giant commits containing unrelated work.

---

## 39. AI Coding Rules

Cursor and Claude Code are implementation assistants, not architects.

Before large implementation tasks:

1. Inspect existing code.
2. Understand dependencies.
3. Identify affected components.
4. Create an implementation plan.
5. Implement.
6. Run tests.
7. Review diff.
8. Review security.
9. Update documentation.

Never blindly accept large generated changes.

Never rewrite entire directories when a targeted change is sufficient.

---

## 40. Definition of High-Quality Code

A feature is not complete because:

"it works on my machine."

A feature is complete when:

- It works
- It is tested
- It is typed
- It handles errors
- It is observable
- It is secure
- It respects tenant boundaries
- It is documented
- It can be deployed reproducibly

---

## 41. Architecture Quality Bar

Every major architectural decision should be evaluated against:

Correctness
Security
Reliability
Maintainability
Observability
Scalability
Cost
Developer experience

Do not choose technology because it sounds impressive.

Choose it because it solves a real requirement.

---

## 42. Golden Rule

The system should be:

BORING WHERE IT SHOULD BE BORING.

Use deterministic engineering for:

- APIs
- databases
- authorization
- execution
- infrastructure
- calculations

Use AI where AI provides genuine value:

- reasoning
- interpretation
- planning
- synthesis
- recommendations

This separation is one of the most important architectural principles of MerchantOS.

---

## 43. Final Architecture Philosophy

MerchantOS should demonstrate:

AI intelligence
+
strong software engineering
+
safe autonomy
+
cloud infrastructure
+
measurable reliability

The goal is not to prove that an LLM can write code.

The goal is to prove that we can design and ship a reliable AI-powered system.
