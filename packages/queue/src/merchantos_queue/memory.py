"""In-memory queue for unit tests. Not a production adapter."""

from merchantos_domain import QueueMessage


class InMemoryQueue:
    def __init__(self) -> None:
        self.messages: list[QueueMessage] = []

    def ping(self) -> None:
        return None

    def enqueue(self, message: QueueMessage) -> None:
        if message.model_dump().keys() & {"merchant_id", "store_id", "token"}:
            raise ValueError("queue messages must not carry tenant or secrets")
        self.messages.append(message)
