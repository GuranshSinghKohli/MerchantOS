from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern="^(system|user)$")
    content: str = Field(max_length=12_000)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: str | None = None


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    data: T
    usage: LLMUsage


class LLMPort(Protocol):
    """Provider-agnostic completion. Never carries API keys in messages or results."""

    def complete[T: BaseModel](
        self,
        messages: Sequence[LLMMessage],
        schema: type[T],
        *,
        timeout_seconds: float,
    ) -> LLMResult[T]: ...
