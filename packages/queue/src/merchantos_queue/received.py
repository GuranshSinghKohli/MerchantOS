from dataclasses import dataclass

from merchantos_domain import QueueMessage


@dataclass(frozen=True)
class ReceivedMessage:
    message: QueueMessage
    receipt_handle: str
