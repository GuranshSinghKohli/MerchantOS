from uuid import uuid4

from merchantos_domain import QueueMessage
from merchantos_domain.queue_message import JobKind
from merchantos_queue.factory import create_queue
from merchantos_queue.memory import InMemoryQueue


def test_in_memory_enqueue() -> None:
    queue = InMemoryQueue()
    message = QueueMessage(job_kind=JobKind.SYNC, job_id=uuid4())
    queue.ping()
    queue.enqueue(message)
    assert queue.messages == [message]


def test_factory_without_endpoint_is_memory() -> None:
    queue = create_queue(
        endpoint_url=None,
        queue_name="x",
        region="us-east-1",
        access_key_id="local",
        secret_access_key="local",
        environment="dev",
    )
    assert isinstance(queue, InMemoryQueue)
