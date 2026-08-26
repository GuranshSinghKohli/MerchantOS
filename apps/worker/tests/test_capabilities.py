from inspect import signature

from merchantos_worker.capabilities import AgentCapabilities, SyncCapabilities, WebhookCapabilities
from merchantos_worker.handlers.agent import handle_agent_run


def test_sync_capabilities_are_reader_only() -> None:
    assert "mutator" not in SyncCapabilities.__dataclass_fields__
    assert "llm" not in SyncCapabilities.__dataclass_fields__
    assert list(SyncCapabilities.__dataclass_fields__) == ["reader"]


def test_webhook_capabilities_are_reader_only() -> None:
    assert "mutator" not in WebhookCapabilities.__dataclass_fields__
    assert list(WebhookCapabilities.__dataclass_fields__) == ["reader"]


def test_agent_capabilities_have_no_mutator() -> None:
    assert list(AgentCapabilities.__dataclass_fields__) == ["tools", "llm"]
    assert "mutator" not in AgentCapabilities.__dataclass_fields__
    params = signature(handle_agent_run).parameters
    assert "caps" in params
    assert "AgentCapabilities" in str(params["caps"].annotation)
