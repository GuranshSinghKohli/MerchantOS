import pytest
from merchantos_queue.elasticmq_dev import ElasticMqDevQueue
from merchantos_queue.factory import create_queue


def test_dev_adapter_rejects_aws_endpoint() -> None:
    with pytest.raises(ValueError, match="production"):
        ElasticMqDevQueue(
            endpoint_url="https://sqs.us-east-1.amazonaws.com",
            queue_name="jobs",
            region="us-east-1",
            access_key_id="local",
            secret_access_key="local",
        )


def test_factory_rejects_dev_adapter_outside_dev() -> None:
    with pytest.raises(RuntimeError, match="not allowed outside dev"):
        create_queue(
            endpoint_url="http://localhost:9324",
            queue_name="jobs",
            region="us-east-1",
            access_key_id="local",
            secret_access_key="local",
            environment="staging",
        )
