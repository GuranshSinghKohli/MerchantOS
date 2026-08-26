"""Capability-isolated worker handlers (ADR 0012).

SyncCapabilities has ShopifyReader only.
WebhookCapabilities has reader + projection writer (via handler).
Neither includes ShopifyMutator, LLM, or credentials objects.
"""

from dataclasses import dataclass

from merchantos_llm import LLMPort
from merchantos_mcp import ToolRegistry
from merchantos_queue import QueuePort
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.reader import ShopifyReader
from sqlalchemy import Engine


@dataclass(frozen=True)
class SyncCapabilities:
    reader: ShopifyReader


@dataclass(frozen=True)
class WebhookCapabilities:
    reader: ShopifyReader


@dataclass(frozen=True)
class AgentCapabilities:
    """Read tools + LLM only. No ShopifyMutator, credentials, or raw engine execute."""

    tools: ToolRegistry
    llm: LLMPort


def fake_agent_capabilities() -> AgentCapabilities:
    from merchantos_llm import FakeLLM, default_orchestrator_turns
    from merchantos_mcp import build_commerce_registry

    class _Unused:
        pass

    return AgentCapabilities(
        tools=build_commerce_registry(_Unused()),  # type: ignore[arg-type]
        llm=FakeLLM(default_orchestrator_turns()),
    )


@dataclass(frozen=True)
class WorkerRuntime:
    engine: Engine
    queue: QueuePort
    sync: SyncCapabilities
    webhook: WebhookCapabilities
    agent: AgentCapabilities
    encryptor: TokenEncryptor | None
    owner: str
