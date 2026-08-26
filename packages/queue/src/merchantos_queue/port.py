from typing import Protocol

from merchantos_domain import QueueMessage


class QueuePort(Protocol):
    def ping(self) -> None:
        """Raise if the broker is unreachable."""

    def enqueue(self, message: QueueMessage) -> None:
        """Persist a job identifier. Production AWS adapter lands in a later phase."""
