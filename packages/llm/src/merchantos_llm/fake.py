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


_INTEL_TOOLS = {
    "analytics": ("get_revenue_metrics",),
    "inventory": ("get_inventory_health",),
    "customer": ("get_customer_metrics",),
}
_INTEL_CATEGORY = {
    "analytics": "revenue",
    "inventory": "inventory",
    "customer": "customer",
}


def default_intelligence_turns(selected: Sequence[str]) -> list[FakeTurn]:
    """Scripted specialist + synthesis + recommend turns for CI FakeLLM."""
    turns: list[FakeTurn] = []
    for name in selected:
        tools = _INTEL_TOOLS.get(name, ("get_store_overview",))
        category = _INTEL_CATEGORY.get(name, "other")
        turns.append(
            FakeTurn(
                {
                    "plan": f"collect {name} evidence",
                    "tools": [{"name": tool, "arguments": {"preset": "last_30"}} for tool in tools],
                    "insufficient_data": False,
                }
            )
        )
        turns.append(
            FakeTurn(
                {
                    "summary": f"{name} metrics are taken from allowlisted tools.",
                    "findings": [
                        {
                            "title": f"{name} snapshot",
                            "description": f"{name} metrics are taken from allowlisted tools.",
                            "category": category,
                            "severity": "watch",
                            "claim_kind": "FACT",
                            "evidence_ids": ["ev_1"],
                            "limitations": [],
                        }
                    ],
                    "assumptions": [],
                    "limitations": [],
                    "next_steps": ["review the next period"],
                    "uncertainty": "",
                    "insufficient_data": False,
                    "proposed_confidence": "MEDIUM",
                }
            )
        )
    evidence_ids = [f"{name}:ev_1" for name in selected] or ["analytics:ev_1"]
    finding_ids = [f"{name}:f_1" for name in selected]
    turns.append(
        FakeTurn(
            {
                "executive_summary": "Specialist metrics coincide in the selected window.",
                "insights": [
                    {
                        "title": "Cross-agent snapshot",
                        "description": "Specialist metrics coincide in the selected window.",
                        "kind": "CORRELATION" if len(selected) > 1 else "OBSERVATION",
                        "evidence_ids": evidence_ids,
                        "finding_ids": finding_ids,
                        "limitations": [],
                    }
                ],
                "limitations": [],
                "proposed_confidence": "MEDIUM",
            }
        )
    )
    turns.append(
        FakeTurn(
            {
                "recommendations": [
                    {
                        "title": "Review the latest specialist signals",
                        "recommendation": (
                            "Investigate the metrics cited by the selected specialists."
                        ),
                        "rationale": "Evidence from allowlisted tools supports a review.",
                        "evidence_ids": evidence_ids,
                        "insight_ids": ["ins_1"],
                        "finding_ids": finding_ids,
                        "expected_objective": "Understand current performance",
                        "proposed_priority": "MEDIUM",
                        "limitations": ["Advisory only"],
                    }
                ],
                "proposed_confidence": "MEDIUM",
            }
        )
    )
    return turns


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
