from merchantos_queue.aws import AwsSqsQueue
from merchantos_queue.elasticmq_dev import ElasticMqDevQueue
from merchantos_queue.memory import InMemoryQueue
from merchantos_queue.port import QueuePort

_AWS_ENVS = frozenset({"staging", "production"})


def create_queue(
    *,
    endpoint_url: str | None,
    queue_name: str,
    region: str,
    access_key_id: str,
    secret_access_key: str,
    environment: str,
    queue_url: str | None = None,
) -> QueuePort:
    """InMemory or ElasticMQ in dev. AWS SQS in staging/production via task role."""
    if environment in _AWS_ENVS:
        if endpoint_url:
            raise RuntimeError("SQS_ENDPOINT_URL is not allowed outside dev")
        return AwsSqsQueue(queue_name=queue_name, region=region, queue_url=queue_url)
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
