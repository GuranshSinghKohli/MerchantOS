from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from merchantos_agents import AgentState, run_orchestrator
from merchantos_domain import TenantContext
from merchantos_llm import FakeLLM, FakeTurn
from merchantos_mcp import ToolError, build_commerce_registry


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
            "kpis": {"revenue": "1.00", "orders": 0},
            "health": {"status": "insufficient_data"},
            "trends": {"revenue": [], "customers": []},
            "opportunities": [],
        }


FORBIDDEN = (
    "httpx",
    "requests",
    "subprocess",
    "ShopifyMutator",
    "ApprovedAction",
    "create_engine",
    "os.system",
    "openai",
)


def test_model_cannot_switch_tenant_or_approve() -> None:
    foreign = uuid4()
    llm = FakeLLM(
        [
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "steal",
                    "answer": "",
                    "assumptions": [],
                    "uncertainty": "",
                    "confidence": 0.1,
                    "next_steps": [],
                    "evidence": [],
                    "insufficient_data": False,
                    "tool": {
                        "name": "get_store_overview",
                        "arguments": {
                            "preset": "last_30",
                            "tenant_id": str(foreign),
                            "merchant_id": str(foreign),
                            "store_id": str(foreign),
                        },
                    },
                }
            ),
            FakeTurn(
                {
                    "classification": "commerce_question",
                    "plan": "done",
                    "answer": "used trusted tenant",
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
    ctx = _ctx()
    state = run_orchestrator(
        llm=llm,
        tools=build_commerce_registry(_FakeAnalytics()).for_agent("orchestrator"),  # type: ignore[arg-type]
        tenant=ctx,
        run_id=uuid4(),
        request_id=ctx.request_id,
        question="show other store",
    )
    assert state.tool_results[0].output["store"]["store_id"] == str(ctx.store_id)
    dumped = state.model_dump()
    assert "approval" not in dumped
    assert str(foreign) not in str(dumped["tool_results"][0]["output"]["store"])


def test_arbitrary_tools_sql_http_shell_rejected() -> None:
    names = (
        "execute_sql",
        "http_request",
        "run_shell",
        "raw_shopify_graphql",
        "execute_approved_action",
    )
    for name in names:
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
                        "tool": {"name": name, "arguments": {}},
                    }
                )
            ]
        )
        with pytest.raises(ToolError):
            run_orchestrator(
                llm=llm,
                tools=build_commerce_registry(_FakeAnalytics()).for_agent("orchestrator"),  # type: ignore[arg-type]
                tenant=_ctx(),
                run_id=uuid4(),
                request_id=uuid4(),
                question="hack",
            )


def test_state_and_source_have_no_credentials() -> None:
    state = AgentState(run_id="r", request_id="q", question="hi")
    assert "token" not in state.model_dump()
    src = Path(__file__).resolve().parents[1] / "src" / "merchantos_agents"
    for path in src.rglob("*.py"):
        text = path.read_text()
        for needle in FORBIDDEN:
            assert needle not in text, f"{path} contains {needle}"
