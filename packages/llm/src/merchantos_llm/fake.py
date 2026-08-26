from collections.abc import Sequence
from time import sleep
from typing import TypeVar

from merchantos_domain import LLMTimeoutError, ProviderFailureError
from pydantic import BaseModel, ValidationError

from merchantos_llm.port import LLMMessage, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


class FakeTurn:
    def __init__(
        self,
        output: dict[str, object] | None = None,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.output = output
        self.error = error
        self.delay_seconds = delay_seconds


class FakeLLM:
    """Deterministic scripted model. Used in CI and AgentBench fake lane."""

    def __init__(self, turns: Sequence[FakeTurn], *, model: str = "fake") -> None:
        self._turns = list(turns)
        self.calls: list[tuple[LLMMessage, ...]] = []
        self.model = model

    def complete(
        self,
        messages: Sequence[LLMMessage],
        schema: type[T],
        *,
        timeout_seconds: float,
    ) -> LLMResult[T]:
        self.calls.append(tuple(messages))
        if not self._turns:
            raise ProviderFailureError("FakeLLM has no remaining turns")
        turn = self._turns.pop(0)
        if turn.delay_seconds > timeout_seconds:
            raise LLMTimeoutError("llm timed out")
        if turn.delay_seconds:
            sleep(min(turn.delay_seconds, 0.05))
        if turn.error is not None:
            raise turn.error
        if turn.output is None:
            raise ProviderFailureError("FakeLLM turn has no output")
        try:
            data = schema.model_validate(turn.output)
        except ValidationError as exc:
            raise exc
        return LLMResult(
            data=data,
            usage=LLMUsage(
                model=self.model,
                input_tokens=1,
                output_tokens=1,
                estimated_cost_usd="0",
            ),
        )


def default_orchestrator_turns() -> list[FakeTurn]:
    return [
        FakeTurn(
            {
                "classification": "commerce_question",
                "plan": "Read store overview, then answer.",
                "answer": "",
                "assumptions": ["Projection data is current."],
                "uncertainty": "Metrics depend on synced orders.",
                "confidence": 0.6,
                "next_steps": ["Review the overview KPIs."],
                "evidence": [],
                "insufficient_data": False,
                "tool": {"name": "get_store_overview", "arguments": {"preset": "last_30"}},
            }
        ),
        FakeTurn(
            {
                "classification": "commerce_question",
                "plan": "Ground the answer in tool evidence.",
                "answer": "Store overview retrieved from MerchantOS analytics.",
                "assumptions": ["Included paid orders only."],
                "uncertainty": "Short history reduces confidence.",
                "confidence": 0.7,
                "next_steps": ["Inspect revenue and inventory next."],
                "evidence": [{"source": "get_store_overview", "fact": "overview loaded"}],
                "insufficient_data": False,
                "tool": None,
            }
        ),
    ]
