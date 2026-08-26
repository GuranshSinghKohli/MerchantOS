from merchantos_queue.elasticmq_dev import ElasticMqDevQueue
from merchantos_queue.memory import InMemoryQueue
from merchantos_queue.port import QueuePort


def create_queue(
    *,
    endpoint_url: str | None,
    queue_name: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    environment: str,
) -> QueuePort:
    """Return InMemory when unset, ElasticMQ only in dev with a local endpoint."""
    if not endpoint_url:
        return InMemoryQueue()
    if environment != "dev":
        raise RuntimeError("ElasticMqDevQueue is development-only; unset SQS_ENDPOINT_URL")
    return ElasticMqDevQueue(
        endpoint_url=endpoint_url,
        queue_name=queue_name,
        region=region,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )
