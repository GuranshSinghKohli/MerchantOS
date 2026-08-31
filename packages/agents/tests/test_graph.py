from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_agents import OrchestratorOutput, run_orchestrator, to_ask_result
from merchantos_domain import (
    InvalidModelOutputError,
    LLMTimeoutError,
    ProviderFailureError,
    TenantContext,
)
from merchantos_llm import FakeLLM, FakeTurn
from merchantos_mcp import ToolError, build_commerce_registry
from pydantic import ValidationError


def _ctx() -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=uuid4(),
            store_id=uuid4(),
            user_id=uuid4(),
            request_id=uuid4(),
            scopes=("read_orders",),
        )
    )


class _FakeAnalytics:
    def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
        return {
            "request_id": str(ctx.request_id),
            "store": {"store_id": str(ctx.store_id), "shop_domain": "alpha.myshopify.com"},
            "kpis": {"revenue": "100.00", "orders": 1},
            "health": {"status": "watch", "score": 70},
            "trends": {"revenue": [], "customers": []},
            "opportunities": [],
        }


def _registry():
    return build_commerce_registry(_FakeAnalytics())  # type: ignore[arg-type]


def test_graph_completes_and_invokes_overview() -> None:
    llm = FakeLLM(
        [
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "read overview",
                    "answer": "",
                    "assumptions": [],
                    "uncertainty": "",
                    "confidence": 0.5,
                    "next_steps": [],
                    "evidence": [],
                    "insufficient_data": False,
                    "tool": {"name": "get_store_overview", "arguments": {"preset": "last_30"}},
                }
            ),
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "answer",
                    "answer": "Revenue is 100.00 from analytics.",
                    "assumptions": ["paid orders"],
                    "uncertainty": "low history",
                    "confidence": 0.7,
                    "next_steps": ["review inventory"],
                    "evidence": [{"source": "get_store_overview", "fact": "revenue=100.00"}],
                    "insufficient_data": False,
                    "tool": None,
                }
            ),
        ]
    )
    ctx = _ctx()
    state = run_orchestrator(
        llm=llm,
        tools=_registry().for_agent("orchestrator"),
        tenant=ctx,
        run_id=uuid4(),
        request_id=ctx.request_id,
        question="How is my store?",
    )
    result = to_ask_result(state)
    assert result.answer.startswith("Revenue")
    assert state.tool_results[0].ok is True
    assert state.tool_results[0].output["store"]["store_id"] == str(ctx.store_id)
    assert "tenant_id" not in state.model_dump()


def test_unknown_tool_is_rejected() -> None:
    llm = FakeLLM(
        [
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "bad",
                    "answer": "",
                    "assumptions": [],
                    "uncertainty": "",
                    "confidence": 0.1,
                    "next_steps": [],
                    "evidence": [],
                    "insufficient_data": False,
                    "tool": {"name": "execute_sql", "arguments": {}},
                }
            )
        ]
    )
    with pytest.raises(ToolError):
        run_orchestrator(
            llm=llm,
            tools=_registry().for_agent("orchestrator"),
            tenant=_ctx(),
            run_id=uuid4(),
            request_id=uuid4(),
            question="run sql",
        )


def test_invalid_output_exhausts_retries() -> None:
    llm = FakeLLM([FakeTurn({"nope": True}), FakeTurn({"nope": True}), FakeTurn({"nope": True})])
    with pytest.raises(InvalidModelOutputError):
        run_orchestrator(
            llm=llm,
            tools=_registry().for_agent("orchestrator"),
            tenant=_ctx(),
            run_id=uuid4(),
            request_id=uuid4(),
            question="hi",
        )


def test_provider_and_timeout_errors_propagate() -> None:
    with pytest.raises(ProviderFailureError):
        run_orchestrator(
            llm=FakeLLM([FakeTurn(error=ProviderFailureError("down"))]),
            tools=_registry().for_agent("orchestrator"),
            tenant=_ctx(),
            run_id=uuid4(),
            request_id=uuid4(),
            question="hi",
        )
    with pytest.raises(LLMTimeoutError):
        run_orchestrator(
            llm=FakeLLM([FakeTurn({"answer": "x"}, delay_seconds=9)]),
            tools=_registry().for_agent("orchestrator"),
            tenant=_ctx(),
            run_id=uuid4(),
            request_id=uuid4(),
            question="hi",
        )


def test_orchestrator_redacts_emails_from_llm_context() -> None:
    class _PiiAnalytics(_FakeAnalytics):
        def overview(self, ctx: TenantContext, filters: object) -> dict[str, object]:
            body = super().overview(ctx, filters)
            body["products"] = [
                {"product_gid": "gid://shopify/Product/1", "title": "Contact jane@shop.test"}
            ]
            return body

    llm = FakeLLM(
        [
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "read",
                    "answer": "",
                    "assumptions": [],
                    "uncertainty": "",
                    "confidence": 0.4,
                    "next_steps": [],
                    "evidence": [],
                    "insufficient_data": False,
                    "tool": {"name": "get_store_overview", "arguments": {"preset": "last_30"}},
                }
            ),
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "answer",
                    "answer": "Overview loaded.",
                    "assumptions": [],
                    "uncertainty": "",
                    "confidence": 0.5,
                    "next_steps": [],
                    "evidence": [],
                    "insufficient_data": False,
                    "tool": None,
                }
            ),
        ]
    )
    run_orchestrator(
        llm=llm,
        tools=build_commerce_registry(_PiiAnalytics()).for_agent("orchestrator"),  # type: ignore[arg-type]
        tenant=_ctx(),
        run_id=uuid4(),
        request_id=uuid4(),
        question="Email ada@example.com about revenue",
    )
    blob = str(llm.calls)
    assert "jane@shop.test" not in blob
    assert "ada@example.com" not in blob
    assert "[redacted]" in blob


def test_orchestrator_output_rejects_approval() -> None:
    with pytest.raises(ValidationError):
        OrchestratorOutput.model_validate(
            {
                "classification": "commerce_question",
                "status": "APPROVED",
                "tenant_id": "x",
            }
        )
