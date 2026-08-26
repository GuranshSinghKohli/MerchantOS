from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from merchantos_app import AnalyticsService, AskService
from merchantos_db import AgentRunRepository, session_scope
from merchantos_domain import AgentRunStatus, ProviderFailureError, TenantContext, TransientJobError
from merchantos_llm import FakeLLM, FakeTurn
from merchantos_mcp import build_commerce_registry
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_worker.capabilities import AgentCapabilities
from merchantos_worker.handlers.agent import handle_agent_run
from merchantos_worker.testing import seed_installed_store
from sqlalchemy.engine import Engine

TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
pytestmark = pytest.mark.integration


def _ctx(view) -> TenantContext:
    return TenantContext.from_session(
        SimpleNamespace(
            merchant_id=view.merchant_id,
            store_id=view.store_id,
            user_id=view.user_id,
            request_id=uuid4(),
            scopes=view.scopes,
        )
    )


def test_agent_worker_completes_and_is_idempotent(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as session:
        view = seed_installed_store(session, shop="agent-a.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    created = AskService(postgres).enqueue(ctx, "How is the store?")
    rid = UUID(str(created["run_id"]))
    caps = AgentCapabilities(
        tools=build_commerce_registry(AnalyticsService(postgres)),
        llm=FakeLLM(
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
                        "answer": "Deterministic overview answer.",
                        "assumptions": [],
                        "uncertainty": "",
                        "confidence": 0.6,
                        "next_steps": [],
                        "evidence": [{"source": "get_store_overview", "fact": "loaded"}],
                        "insufficient_data": False,
                        "tool": None,
                    }
                ),
            ]
        ),
    )
    handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w1")
    with session_scope(postgres) as session:
        row = AgentRunRepository(session).get(rid)
        assert row is not None
        assert row.status == AgentRunStatus.COMPLETED.value
        calls = AgentRunRepository(session).list_tool_calls(ctx, rid)
        assert [item.tool_name for item in calls] == ["get_store_overview"]
    handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w1")
    with session_scope(postgres) as session:
        row = AgentRunRepository(session).get(rid)
        assert row is not None
        assert row.status == AgentRunStatus.COMPLETED.value


def test_retry_then_exhaustion(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as session:
        view = seed_installed_store(session, shop="agent-fail.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    created = AskService(postgres).enqueue(ctx, "retry please")
    rid = UUID(str(created["run_id"]))
    caps = AgentCapabilities(
        tools=build_commerce_registry(AnalyticsService(postgres)),
        llm=FakeLLM(
            [
                FakeTurn(error=ProviderFailureError("down")),
                FakeTurn(error=ProviderFailureError("down")),
                FakeTurn(error=ProviderFailureError("down")),
            ]
        ),
    )
    with pytest.raises(TransientJobError):
        handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w1")
    with pytest.raises(TransientJobError):
        handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w1")
    handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w1")
    with session_scope(postgres) as session:
        row = AgentRunRepository(session).get(rid)
        assert row is not None
        assert row.status == AgentRunStatus.FAILED.value
        assert row.error_code
        assert "Traceback" not in (row.error_message or "")


def test_specialist_run_persists_agent_and_tools(postgres: Engine) -> None:
    encryptor = TokenEncryptor.from_urlsafe_key(TEST_KEY, "test")
    with session_scope(postgres) as session:
        view = seed_installed_store(session, shop="agent-spec.myshopify.com", encryptor=encryptor)
        ctx = _ctx(view)
    created = AskService(postgres).enqueue(ctx, "Why did revenue change?")
    rid = UUID(str(created["run_id"]))
    caps = AgentCapabilities(
        tools=build_commerce_registry(AnalyticsService(postgres)),
        llm=FakeLLM(
            [
                FakeTurn(
                    {
                        "classification": "commerce_question",
                        "plan": "route analytics",
                        "answer": "",
                        "assumptions": [],
                        "uncertainty": "",
                        "confidence": 0.4,
                        "next_steps": [],
                        "evidence": [],
                        "insufficient_data": False,
                        "tool": None,
                        "specialist": "analytics",
                    }
                ),
                FakeTurn(
                    {
                        "plan": "read revenue",
                        "tools": [
                            {"name": "get_revenue_metrics", "arguments": {"preset": "last_30"}}
                        ],
                        "insufficient_data": False,
                    }
                ),
                FakeTurn(
                    {
                        "summary": "Revenue metrics loaded from analytics.",
                        "findings": [
                            {
                                "title": "Revenue snapshot",
                                "description": "Revenue is taken from get_revenue_metrics.",
                                "category": "revenue",
                                "severity": "info",
                                "claim_kind": "FACT",
                                "evidence_ids": ["ev_1"],
                                "limitations": [],
                            }
                        ],
                        "assumptions": [],
                        "limitations": [],
                        "next_steps": ["compare next period"],
                        "uncertainty": "",
                        "insufficient_data": False,
                        "proposed_confidence": "MEDIUM",
                    }
                ),
            ]
        ),
    )
    handle_agent_run(engine=postgres, caps=caps, job_id=rid, owner="w-spec")
    with session_scope(postgres) as session:
        row = AgentRunRepository(session).get(rid)
        assert row is not None
        assert row.status == AgentRunStatus.COMPLETED.value
        assert row.classification == "analytics"
        assert row.result_json is not None
        assert "analytics" in row.result_json
        assert "shpua_" not in row.result_json
        calls = AgentRunRepository(session).list_tool_calls(ctx, rid)
        assert [item.tool_name for item in calls] == ["get_revenue_metrics"]
        assert all("@" not in (item.output_redacted or "") for item in calls)
