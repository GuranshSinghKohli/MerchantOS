"""In-memory queue for unit tests. Not a production adapter."""

from uuid import uuid4

from merchantos_domain import QueueMessage

from merchantos_queue.received import ReceivedMessage


class InMemoryQueue:
    def __init__(self) -> None:
        self.messages: list[QueueMessage] = []
        self._inflight: dict[str, QueueMessage] = {}

    def ping(self) -> None:
        return None

    def enqueue(self, message: QueueMessage) -> None:
        if message.model_dump().keys() & {"merchant_id", "store_id", "token"}:
            raise ValueError("queue messages must not carry tenant or secrets")
        self.messages.append(message)

    def receive(
        self,
        *,
        max_messages: int = 1,
        wait_seconds: int = 0,
        visibility_timeout: int = 60,
    ) -> list[ReceivedMessage]:
        _ = wait_seconds, visibility_timeout
        out: list[ReceivedMessage] = []
        for _i in range(min(max_messages, len(self.messages))):
            message = self.messages.pop(0)
            handle = str(uuid4())
            self._inflight[handle] = message
            out.append(ReceivedMessage(message=message, receipt_handle=handle))
        return out

    def delete(self, receipt_handle: str) -> None:
        self._inflight.pop(receipt_handle, None)

    def nack(self, receipt_handle: str) -> None:
        message = self._inflight.pop(receipt_handle, None)
        if message is not None:
            self.messages.append(message)
