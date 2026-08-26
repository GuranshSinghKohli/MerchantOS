"""Phase 1 capability placeholders.

Handlers receive only what they need. No Shopify mutator, LLM, credentials,
or raw SQL engine is attached to an agent capability object.
"""

from dataclasses import dataclass

from merchantos_queue import QueuePort


@dataclass(frozen=True)
class IdleWorkerCapabilities:
    """Phase 1: connectivity only. Job handlers land in later phases."""

    queue: QueuePort
