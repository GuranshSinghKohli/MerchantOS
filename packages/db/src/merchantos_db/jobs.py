from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from merchantos_domain import JobKind, TenantContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from merchantos_db.ids import uuid7
from merchantos_db.models import OutboxMessage, Store, SyncJob, WebhookEvent
from merchantos_db.rls import tenant_scope

SYNC_RESOURCES: tuple[str, ...] = (
    "locations",
    "products",
    "customers",
    "orders",
    "inventory",
)


@dataclass
class SyncJobIdentity:
    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue_sync(
        self,
        ctx: TenantContext,
        *,
        kind: str,
        idempotency_prefix: str,
    ) -> list[SyncJob]:
        with tenant_scope(self._session, ctx.merchant_id):
            existing = list(
                self._session.scalars(
                    select(SyncJob).where(
                        SyncJob.merchant_id == ctx.merchant_id,
                        SyncJob.store_id == ctx.store_id,
                        SyncJob.kind == kind,
                        SyncJob.status.in_(("pending", "running")),
                    )
                )
            )
            if existing:
                return existing
            jobs: list[SyncJob] = []
            for resource in SYNC_RESOURCES:
                job = SyncJob(
                    id=uuid7(),
                    merchant_id=ctx.merchant_id,
                    store_id=ctx.store_id,
                    user_id=ctx.user_id,
                    request_id=ctx.request_id,
                    kind=kind,
                    resource=resource,
                    status="pending",
                    idempotency_key=f"{idempotency_prefix}:{resource}:{uuid7()}",
                )
                self._session.add(job)
                self._session.add(
                    OutboxMessage(
                        merchant_id=ctx.merchant_id,
                        job_kind=JobKind.SYNC.value,
                        job_id=job.id,
                    )
                )
                jobs.append(job)
            store = self._session.get(Store, ctx.store_id)
            if store is not None and store.merchant_id == ctx.merchant_id:
                store.sync_status = "pending"
                store.sync_error = None
            self._session.flush()
            return jobs

    def list_sync_jobs(self, ctx: TenantContext) -> list[SyncJob]:
        with tenant_scope(self._session, ctx.merchant_id):
            return list(
                self._session.scalars(
                    select(SyncJob)
                    .where(
                        SyncJob.merchant_id == ctx.merchant_id,
                        SyncJob.store_id == ctx.store_id,
                    )
                    .order_by(SyncJob.created_at.desc())
                )
            )

    def get_sync_job(self, job_id: UUID) -> SyncJob | None:
        return self._session.get(SyncJob, job_id)

    def acquire_sync_lease(
        self, job_id: UUID, *, owner: str, now: datetime, ttl: timedelta
    ) -> SyncJob | None:
        job = self._session.get(SyncJob, job_id)
        if job is None:
            return None
        if (
            job.lease_until is not None
            and job.lease_until > now
            and job.lease_owner is not None
            and job.lease_owner != owner
        ):
            return None
        job.status = "running"
        job.attempt = job.attempt + 1
        job.lease_owner = owner
        job.lease_until = now + ttl
        if job.started_at is None:
            job.started_at = now
        store = self._session.get(Store, job.store_id)
        if store is not None and store.merchant_id == job.merchant_id:
            store.sync_status = "running"
        self._session.flush()
        return job

    def update_sync_progress(
        self,
        job_id: UUID,
        *,
        cursor: str | None,
        records_processed: int,
        records_failed: int,
    ) -> None:
        job = self._session.get(SyncJob, job_id)
        if job is None:
            return
        job.cursor = cursor
        job.records_processed = records_processed
        job.records_failed = records_failed
        self._session.flush()

    def complete_sync(self, job_id: UUID, *, now: datetime) -> None:
        job = self._session.get(SyncJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.finished_at = now
        job.lease_until = None
        job.error = None
        self._refresh_store_status(job, now)
        self._session.flush()

    def fail_sync(self, job_id: UUID, *, error: str, now: datetime) -> None:
        job = self._session.get(SyncJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.finished_at = now
        job.lease_until = None
        job.error = error[:500]
        store = self._session.get(Store, job.store_id)
        if store is not None and store.merchant_id == job.merchant_id:
            store.sync_status = "failed"
            store.sync_error = job.error
        self._session.flush()

    def _refresh_store_status(self, job: SyncJob, now: datetime) -> None:
        store = self._session.get(Store, job.store_id)
        if store is None or store.merchant_id != job.merchant_id:
            return
        open_rows = list(
            self._session.scalars(
                select(SyncJob).where(
                    SyncJob.merchant_id == job.merchant_id,
                    SyncJob.store_id == job.store_id,
                    SyncJob.status.in_(("pending", "running")),
                )
            )
        )
        if open_rows:
            store.sync_status = "running"
            return
        failed_rows = list(
            self._session.scalars(
                select(SyncJob).where(
                    SyncJob.merchant_id == job.merchant_id,
                    SyncJob.store_id == job.store_id,
                    SyncJob.status == "failed",
                    SyncJob.created_at >= now - timedelta(hours=1),
                )
            )
        )
        if failed_rows:
            store.sync_status = "failed"
            return
        store.sync_status = "completed"
        store.last_synced_at = now
        store.sync_error = None

    def enqueue_webhook_job(self, event: WebhookEvent) -> None:
        if event.merchant_id is None:
            return
        self._session.add(
            OutboxMessage(
                merchant_id=event.merchant_id,
                job_kind=JobKind.WEBHOOK.value,
                job_id=event.id,
            )
        )
        self._session.flush()

    def unpublished_outbox(self, *, limit: int = 50) -> list[OutboxMessage]:
        return list(
            self._session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.created_at)
                .limit(limit)
            )
        )

    def mark_published(self, outbox_id: UUID, *, now: datetime) -> None:
        row = self._session.get(OutboxMessage, outbox_id)
        if row is not None:
            row.published_at = now

    def get_webhook(self, event_pk: UUID) -> WebhookEvent | None:
        return self._session.get(WebhookEvent, event_pk)

    def mark_webhook_status(self, event_pk: UUID, status: str) -> None:
        row = self._session.get(WebhookEvent, event_pk)
        if row is not None:
            row.status = status

    def get_store(self, store_id: UUID) -> Store | None:
        return self._session.get(Store, store_id)

    def last_synced_at(self, ctx: TenantContext) -> datetime | None:
        with tenant_scope(self._session, ctx.merchant_id):
            store = self._session.get(Store, ctx.store_id)
        return None if store is None else store.last_synced_at
