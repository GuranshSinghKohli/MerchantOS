from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from merchantos_db import ActionRepository, session_scope
from merchantos_domain import (
    MAX_ACTION_ATTEMPTS,
    ActionConflictError,
    ActionExpiredError,
    ActionResult,
    ActionStatus,
    ActionType,
    ApprovedAction,
    AuditEventType,
    InvalidActionError,
    NotApprovedError,
    ShopifyThrottledError,
    TenantContext,
    TransientJobError,
)
from merchantos_observability import get_logger
from merchantos_shopify.mutator import MutationOutcome, ProductMutationState, ShopifyMutator
from sqlalchemy import Engine

from merchantos_worker.capabilities import ExecutionCapabilities
from merchantos_worker.credentials import load_store_access

logger = get_logger(__name__)
_LEASE = timedelta(seconds=60)


def _state_dict(state: ProductMutationState) -> dict[str, Any]:
    return {
        "shopify_gid": state.shopify_gid,
        "title": state.title,
        "description": state.description,
        "tags": list(state.tags),
        "status": state.status,
    }


def _materially_changed(before: dict[str, Any], current: ProductMutationState, field: str) -> bool:
    if field == "title":
        return current.title != before.get("title")
    if field == "description":
        return current.description != before.get("description")
    if field == "tags":
        return list(current.tags) != list(before.get("tags") or [])
    if field == "status":
        return current.status != before.get("status")
    return False


def _verified(expected: dict[str, Any], current: ProductMutationState, field: str) -> bool:
    if field == "title":
        return current.title == expected.get("title")
    if field == "description":
        return current.description == expected.get("description")
    if field == "tags":
        return list(current.tags) == list(expected.get("tags") or [])
    if field == "status":
        return current.status == expected.get("status")
    return False


def handle_action_execute(
    *,
    engine: Engine,
    caps: ExecutionCapabilities,
    job_id: UUID,
    owner: str,
    encryptor: object | None,
) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as db:
        repo = ActionRepository(db)
        existing = repo.get(job_id)
        if existing is None:
            return
        if existing.status == ActionStatus.COMPLETED.value:
            return
        identity = repo.identity(job_id)
        approval = None
        if identity is not None:
            ctx_probe = TenantContext.from_job_row(identity)
            approval = repo.get_approval(ctx_probe, job_id)
        row = repo.acquire_lease(job_id, owner=owner, now=now, ttl=_LEASE)
        if row is None or identity is None:
            return
        attempt = row.attempt
        if row.expires_at <= now:
            repo.fail(
                job_id,
                now=now,
                error_code="expired",
                error_message="action expired",
                status=ActionStatus.EXPIRED.value,
            )
            repo.write_audit(
                TenantContext.from_job_row(identity),
                event_type=AuditEventType.ACTION_EXPIRED.value,
                action_id=row.id,
                actor_type="system",
                actor_id=owner,
                metadata={"error_category": "expired"},
            )
            return
        if "write_products" not in identity.scopes:
            repo.fail(
                job_id,
                now=now,
                error_code="missing_scope",
                error_message="write_products is required",
            )
            repo.write_audit(
                TenantContext.from_job_row(identity),
                event_type=AuditEventType.ACTION_FAILED.value,
                action_id=row.id,
                actor_type="system",
                actor_id=owner,
                metadata={"error_category": "missing_scope"},
            )
            return
        if approval is None:
            repo.fail(job_id, now=now, error_code="not_approved", error_message="missing approval")
            return
        payload = json.loads(row.payload_json)
        before = json.loads(row.before_state_json)
        after = json.loads(row.after_state_json)
        approved = ApprovedAction.load(
            TenantContext.from_job_row(identity),
            action_id=row.id,
            approval_id=approval.id,
            action_status=ActionStatus.APPROVED.value,
            approval_status=approval.status,
            action_merchant_id=row.merchant_id,
            action_store_id=row.store_id,
            action_type=row.action_type,
            payload=payload,
            payload_hash=row.payload_hash,
            frozen_payload_hash=approval.frozen_payload_hash,
            expires_at=row.expires_at,
            now=now,
        )
        ctx = TenantContext.from_job_row(identity)
        repo.write_audit(
            ctx,
            event_type=AuditEventType.ACTION_EXECUTING.value,
            action_id=row.id,
            actor_type="system",
            actor_id=owner,
            metadata={"attempt": attempt},
        )
        action_type = row.action_type
        resource_id = row.resource_id
        gid = row.resource_gid
    access = load_store_access(
        engine,
        merchant_id=identity.merchant_id,
        store_id=identity.store_id,
        user_id=identity.user_id,
        request_id=identity.request_id,
        encryptor=encryptor,  # type: ignore[arg-type]
    )
    mutator = caps.mutator
    field = {
        ActionType.UPDATE_PRODUCT_TITLE.value: "title",
        ActionType.UPDATE_PRODUCT_DESCRIPTION.value: "description",
        ActionType.UPDATE_PRODUCT_TAGS.value: "tags",
        ActionType.UPDATE_PRODUCT_STATUS.value: "status",
    }.get(action_type)
    if field is None:
        with session_scope(engine) as db:
            ActionRepository(db).fail(
                job_id,
                now=datetime.now(UTC),
                error_code="unsupported",
                error_message="not executable",
            )
        return
    try:
        current = mutator.get_product(access.shop_domain, access.access_token, gid)
        if _materially_changed(before, current, field):
            raise ActionConflictError("resource changed since proposal")
        outcome = _mutate(mutator, access.shop_domain, access.access_token, approved, payload)
        if not outcome.ok:
            raise InvalidActionError(outcome.error_code or "mutation_failed")
        verified_state = mutator.get_product(access.shop_domain, access.access_token, gid)
        verified = _verified(after, verified_state, field)
        result = ActionResult(
            ok=verified,
            mutation_name=approved.mutation.value,
            shopify_request_id=outcome.request_id,
            error_code=None if verified else "verification_failed",
            verified=verified,
            before_state=before,
            after_state=_state_dict(verified_state),
            response_redacted={"ok": True, "verified": verified},
        )
        status = ActionStatus.COMPLETED.value if verified else ActionStatus.FAILED.value
        _finish(engine, ctx, job_id, resource_id, result, status, field, after)
    except ActionConflictError as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.CONFLICT.value,
            "conflict",
            retryable=False,
        )
    except ActionExpiredError as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.EXPIRED.value,
            "expired",
            retryable=False,
        )
    except NotApprovedError as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.FAILED.value,
            "not_approved",
            retryable=False,
        )
    except InvalidActionError as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.FAILED.value,
            "invalid",
            retryable=False,
        )
    except (ShopifyThrottledError, TransientJobError) as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.FAILED.value,
            type(exc).__name__,
            retryable=True,
        )
    except Exception as exc:
        _fail(
            engine,
            ctx,
            job_id,
            attempt,
            exc,
            ActionStatus.FAILED.value,
            type(exc).__name__,
            retryable=True,
        )


def _mutate(
    mutator: ShopifyMutator,
    shop: str,
    token: str,
    approved: ApprovedAction,
    payload: dict[str, Any],
) -> MutationOutcome:
    gid = str(payload["shopify_gid"])
    if approved.action_type is ActionType.UPDATE_PRODUCT_TITLE:
        return mutator.update_product_title(shop, token, gid, str(payload["title"]))
    if approved.action_type is ActionType.UPDATE_PRODUCT_DESCRIPTION:
        return mutator.update_product_description(shop, token, gid, str(payload["description"]))
    if approved.action_type is ActionType.UPDATE_PRODUCT_TAGS:
        return mutator.update_product_tags(shop, token, gid, list(payload["tags"]))
    if approved.action_type is ActionType.UPDATE_PRODUCT_STATUS:
        return mutator.update_product_status(shop, token, gid, str(payload["status"]))
    raise InvalidActionError("unsupported mutation")


def _finish(
    engine: Engine,
    ctx: TenantContext,
    job_id: UUID,
    resource_id: UUID,
    result: ActionResult,
    status: str,
    field: str,
    after: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    with session_scope(engine) as db:
        repo = ActionRepository(db)
        existing = repo.get_result(ctx, job_id)
        if existing is not None:
            return
        repo.record_result(ctx, job_id, result)
        repo.set_status(job_id, status, now=now)
        if result.ok:
            kwargs: dict[str, Any] = {}
            if field == "title":
                kwargs["title"] = after.get("title")
            if field == "description":
                kwargs["description"] = after.get("description")
            if field == "tags":
                kwargs["tags"] = list(after.get("tags") or [])
            if field == "status":
                kwargs["status"] = after.get("status")
            repo.update_product_projection(ctx, resource_id, **kwargs)
        repo.write_audit(
            ctx,
            event_type=(
                AuditEventType.ACTION_COMPLETED.value
                if result.ok
                else AuditEventType.ACTION_FAILED.value
            ),
            action_id=job_id,
            actor_type="system",
            actor_id=None,
            metadata={"verified": result.verified, "error_code": result.error_code},
        )
    logger.info(
        "action_executed",
        action_id=str(job_id),
        merchant_id=str(ctx.merchant_id),
        store_id=str(ctx.store_id),
        success=result.ok,
        verified=result.verified,
    )


def _fail(
    engine: Engine,
    ctx: TenantContext,
    job_id: UUID,
    attempt: int,
    exc: Exception,
    status: str,
    code: str,
    *,
    retryable: bool,
) -> None:
    if retryable and attempt < MAX_ACTION_ATTEMPTS:
        logger.warning(
            "action_retry",
            action_id=str(job_id),
            error_category=code,
            retry_count=attempt,
        )
        raise TransientJobError("action will retry") from exc
    now = datetime.now(UTC)
    event = {
        ActionStatus.CONFLICT.value: AuditEventType.ACTION_CONFLICTED.value,
        ActionStatus.EXPIRED.value: AuditEventType.ACTION_EXPIRED.value,
    }.get(status, AuditEventType.ACTION_FAILED.value)
    with session_scope(engine) as db:
        repo = ActionRepository(db)
        repo.fail(job_id, now=now, error_code=code, error_message=str(exc)[:200], status=status)
        repo.write_audit(
            ctx,
            event_type=event,
            action_id=job_id,
            actor_type="system",
            actor_id=None,
            metadata={"error_category": code},
        )
    logger.info(
        "action_failed",
        action_id=str(job_id),
        merchant_id=str(ctx.merchant_id),
        success=False,
        error_category=code,
    )
