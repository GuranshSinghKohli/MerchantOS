from datetime import date
from typing import Literal, Self

from merchantos_domain import CompareMode, DatePreset
from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_LIMIT = 100
MAX_OFFSET = 10_000
MAX_RANGE_DAYS = 366


class DateRangeInput(BaseModel):
    """Shared filters. Tenant fields are not accepted."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    preset: DatePreset = DatePreset.LAST_30
    compare: CompareMode = CompareMode.PREVIOUS_PERIOD
    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("date_from must be on or before date_to")
            if (self.date_to - self.date_from).days > MAX_RANGE_DAYS:
                raise ValueError(f"date range cannot exceed {MAX_RANGE_DAYS} days")
        if self.preset is DatePreset.CUSTOM and (self.date_from is None or self.date_to is None):
            raise ValueError("custom preset requires from and to")
        return self


class ProductPerformanceInput(DateRangeInput):
    limit: int = Field(default=25, ge=1, le=MAX_LIMIT)
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET)
    sort: Literal["revenue", "units", "title", "available"] = "revenue"


class StoreRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_id: str
    shop_domain: str


class ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    store: StoreRef
