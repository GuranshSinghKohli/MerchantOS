from uuid import UUID, uuid4

import pytest
from merchantos_domain import JobKind, QueueMessage
from merchantos_queue.aws import AwsSqsQueue
from merchantos_queue.factory import create_queue


class _Client:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def get_queue_url(self, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/1/{QueueName}"}

    def send_message(self, QueueUrl: str, MessageBody: str) -> dict[str, str]:
        assert "merchant_id" not in MessageBody
        return {"MessageId": "1"}

    def receive_message(self, **kwargs: object) -> dict[str, list[dict[str, str]]]:
        return {
            "Messages": [
                {
                    "Body": ('{"job_kind":"sync","job_id":"00000000-0000-0000-0000-000000000001"}'),
                    "ReceiptHandle": "rh-1",
                }
            ]
        }

    def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:
        self.deleted.append(ReceiptHandle)

    def change_message_visibility(self, **kwargs: object) -> None:
        return None


def test_factory_uses_aws_adapter_outside_dev() -> None:
    queue = create_queue(
        endpoint_url=None,
        queue_name="merchantos-staging-jobs",
        region="us-east-1",
        access_key_id="must-not-be-used",
        secret_access_key="must-not-be-used",
        environment="staging",
        queue_url="https://sqs.us-east-1.amazonaws.com/1/merchantos-staging-jobs",
    )
    assert isinstance(queue, AwsSqsQueue)


def test_factory_rejects_dev_endpoint_in_production() -> None:
    with pytest.raises(RuntimeError, match="not allowed"):
        create_queue(
            endpoint_url="http://localhost:9324",
            queue_name="jobs",
            region="us-east-1",
            access_key_id="local",
            secret_access_key="local",
            environment="production",
        )


def test_aws_queue_round_trip() -> None:
    client = _Client()
    queue = AwsSqsQueue(
        queue_name="jobs",
        region="us-east-1",
        queue_url="https://sqs.us-east-1.amazonaws.com/1/jobs",
        client=client,
    )
    queue.enqueue(QueueMessage(job_kind=JobKind.SYNC, job_id=uuid4()))
    received = queue.receive()
    assert received[0].message.job_id == UUID("00000000-0000-0000-0000-000000000001")
    queue.delete("rh-1")
    assert client.deleted == ["rh-1"]
    queue.ping()
