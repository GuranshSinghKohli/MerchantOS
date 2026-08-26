from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from merchantos_domain.errors import ForbiddenFactoryError
from merchantos_domain.ids import MerchantId, RequestId, StoreId, UserId


class SessionIdentity(Protocol):
    """Trusted session row. Implemented by persistence in a later phase."""

    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


class JobIdentity(Protocol):
    """Trusted persisted job row. Queue bodies must not satisfy this protocol."""

    merchant_id: UUID
    store_id: UUID
    user_id: UUID | None
    request_id: UUID
    scopes: tuple[str, ...]


class TenantContext(BaseModel):
    """Trusted tenant. Construct only via from_session or from_job_row."""

    model_config = ConfigDict(frozen=True)

    merchant_id: MerchantId
    store_id: StoreId
    user_id: UserId | None
    request_id: RequestId
    scopes: tuple[str, ...]

    def __init__(self, **data: object) -> None:
        raise ForbiddenFactoryError(
            "TenantContext must be created via from_session or from_job_row"
        )

    @classmethod
    def model_validate(  # type: ignore[override]
        cls,
        obj: object,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> "TenantContext":
        raise ForbiddenFactoryError(
            "TenantContext.model_validate is forbidden; tenant ids are never accepted from dicts"
        )

    @classmethod
    def from_session(cls, session: SessionIdentity) -> "TenantContext":
        return cls.model_construct(
            merchant_id=MerchantId(session.merchant_id),
            store_id=StoreId(session.store_id),
            user_id=UserId(session.user_id) if session.user_id is not None else None,
            request_id=RequestId(session.request_id),
            scopes=tuple(session.scopes),
        )

    @classmethod
    def from_job_row(cls, row: JobIdentity) -> "TenantContext":
        return cls.model_construct(
            merchant_id=MerchantId(row.merchant_id),
            store_id=StoreId(row.store_id),
            user_id=UserId(row.user_id) if row.user_id is not None else None,
            request_id=RequestId(row.request_id),
            scopes=tuple(row.scopes),
        )


def assert_not_constructible_from_mapping(payload: dict[str, object]) -> None:
    """Contract helper for tests. Always raises."""
    try:
        TenantContext.model_validate(payload)
    except ForbiddenFactoryError:
        raise
    except ValidationError as exc:
        raise ForbiddenFactoryError("dict construction is forbidden") from exc
    raise ForbiddenFactoryError("dict construction unexpectedly succeeded")
