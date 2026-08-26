from datetime import UTC, datetime

from merchantos_db import JobRepository, session_scope
from merchantos_domain import JobKind, QueueMessage
from merchantos_observability import get_logger
from merchantos_queue import QueuePort
from sqlalchemy import Engine

logger = get_logger(__name__)


def publish_unpublished(engine: Engine, queue: QueuePort, *, limit: int = 50) -> int:
    """Relay outbox rows to SQS. At-least-once; consumers are idempotent on job_id."""
    published = 0
    with session_scope(engine) as db:
        rows = JobRepository(db).unpublished_outbox(limit=limit)
        ids = [(row.id, row.job_kind, row.job_id) for row in rows]
    for outbox_id, job_kind, job_id in ids:
        try:
            queue.enqueue(QueueMessage(job_kind=JobKind(job_kind), job_id=job_id))
        except Exception:
            logger.warning("outbox_publish_failed", job_id=str(job_id), job_kind=job_kind)
            continue
        with session_scope(engine) as db:
            JobRepository(db).mark_published(outbox_id, now=datetime.now(UTC))
        published += 1
    return published
