from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from merchantos_app import AnalyticsFilters, AnalyticsService
from merchantos_domain import CompareMode, DatePreset

from merchantos_api.deps import db_engine
from merchantos_api.session_auth import tenant_from_request

router = APIRouter(prefix="/api/v1", tags=["analytics"])

PresetQ = Annotated[DatePreset, Query()]
CompareQ = Annotated[CompareMode, Query()]
FromQ = Annotated[date | None, Query(alias="from")]
ToQ = Annotated[date | None, Query(alias="to")]
LimitQ = Annotated[int, Query(ge=1, le=100)]
OffsetQ = Annotated[int, Query(ge=0)]
SortQ = Annotated[str, Query()]


def _filters(
    request: Request,
    preset: DatePreset,
    compare: CompareMode,
    date_from: date | None,
    date_to: date | None,
    *,
    limit: int = 25,
    offset: int = 0,
    sort: str = "revenue",
) -> AnalyticsFilters:
    return AnalyticsFilters(
        request_id=UUID(str(request.state.request_id)),
        preset=preset,
        compare=compare,
        date_from=date_from,
        date_to=date_to,
        now=datetime.now(UTC),
        limit=limit,
        offset=offset,
        sort=sort,
    )


def _service() -> AnalyticsService:
    return AnalyticsService(db_engine())


@router.get("/overview")
@router.get("/analytics/overview")
def analytics_overview(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().overview(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/revenue")
def analytics_revenue(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().revenue(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/orders")
def analytics_orders(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().orders(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/products")
def analytics_products(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
    limit: LimitQ = 25,
    offset: OffsetQ = 0,
    sort: SortQ = "revenue",
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().products(
        ctx,
        _filters(
            request,
            preset,
            compare,
            date_from,
            date_to,
            limit=limit,
            offset=offset,
            sort=sort,
        ),
    )


@router.get("/analytics/inventory")
def analytics_inventory(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().inventory(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/customers")
def analytics_customers(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().customers(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/health")
def analytics_health(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().health(ctx, _filters(request, preset, compare, date_from, date_to))


@router.get("/analytics/opportunities")
def analytics_opportunities(
    request: Request,
    preset: PresetQ = DatePreset.LAST_30,
    compare: CompareQ = CompareMode.PREVIOUS_PERIOD,
    date_from: FromQ = None,
    date_to: ToQ = None,
) -> dict[str, object]:
    ctx = tenant_from_request(db_engine(), request)
    return _service().opportunities(ctx, _filters(request, preset, compare, date_from, date_to))
