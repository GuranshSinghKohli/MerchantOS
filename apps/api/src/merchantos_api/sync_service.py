from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from merchantos_db import IdentityRepository, JobRepository, session_scope
from merchantos_domain import DomainError, TenantContext
from merchantos_observability import get_logger
from merchantos_queue import QueuePort
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from merchantos_api.publisher import publish_unpublished

logger = get_logger(__name__)


def enqueue_store_sync(
    *,
    engine: Engine,
    queue: QueuePort,
    session_id: UUID,
    request_id: UUID,
    kind: str,
) -> list[dict[str, str]]:
    if kind not in {"initial", "incremental"}:
        raise DomainError("sync kind must be initial or incremental")
    with session_scope(engine) as db:
        identity = IdentityRepository(db).get_session(session_id, request_id, now=datetime.now(UTC))
        ctx = TenantContext.from_session(identity)
        jobs = JobRepository(db).enqueue_sync(
            ctx,
            kind=kind,
            idempotency_prefix=f"{kind}:{ctx.store_id}",
        )
        snapshots = [
            {"id": str(job.id), "resource": job.resource, "status": job.status, "kind": job.kind}
            for job in jobs
        ]
    published = publish_unpublished(engine, queue)
    logger.info(
        "sync_enqueued",
        kind=kind,
        job_count=len(snapshots),
        published=published,
        request_id=str(request_id),
    )
    return snapshots


def list_store_sync(
    *,
    engine: Engine,
    session_id: UUID,
    request_id: UUID,
) -> dict[str, object]:
    with session_scope(engine) as db:
        identity = IdentityRepository(db).get_session(session_id, request_id, now=datetime.now(UTC))
        ctx = TenantContext.from_session(identity)
        JobRepository(db).fail_stale_open_syncs(ctx, now=datetime.now(UTC))
        jobs = JobRepository(db).list_sync_jobs(ctx)
        store = JobRepository(db).get_store(ctx.store_id)
        return {
            "store_sync_status": store.sync_status if store else "unknown",
            "sync_error": store.sync_error if store else None,
            "last_synced_at": store.last_synced_at.isoformat()
            if store is not None and store.last_synced_at
            else None,
            "jobs": [
                {
                    "id": str(job.id),
                    "kind": job.kind,
                    "resource": job.resource,
                    "status": job.status,
                    "records_processed": job.records_processed,
                    "records_failed": job.records_failed,
                    "attempt": job.attempt,
                    "error": job.error,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                }
                for job in jobs
            ],
        }


def enqueue_webhook_outbox(db: Session, event_pk: UUID) -> None:
    repo = JobRepository(db)
    event = repo.get_webhook(event_pk)
    if event is None:
        return
    repo.enqueue_webhook_job(event)
