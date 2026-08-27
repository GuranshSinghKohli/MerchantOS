from typing import Protocol

from merchantos_domain import QueueMessage

from merchantos_queue.received import ReceivedMessage


class QueuePort(Protocol):
    def ping(self) -> None:
        """Raise if the broker is unreachable."""

    def enqueue(self, message: QueueMessage) -> None:
        """Persist a job identifier. Staging/production use AwsSqsQueue."""

    def receive(
        self,
        *,
        max_messages: int = 1,
        wait_seconds: int = 0,
        visibility_timeout: int = 60,
    ) -> list[ReceivedMessage]:
        """At-least-once delivery. Caller must delete or nack."""

    def delete(self, receipt_handle: str) -> None:
        """Ack a received message."""

    def nack(self, receipt_handle: str) -> None:
        """Return a received message for retry."""
