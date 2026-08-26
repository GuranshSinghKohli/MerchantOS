from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobKind(StrEnum):
    AGENT_RUN = "agent_run"
    SYNC = "sync"
    WEBHOOK = "webhook"
    ACTION_EXECUTE = "action_execute"


class QueueMessage(BaseModel):
    """SQS body. Identifiers only — never tenant ids, tokens, or scopes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_kind: JobKind
    job_id: UUID
    traceparent: str | None = None
