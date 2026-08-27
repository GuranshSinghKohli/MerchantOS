"""AWS SQS adapter for staging and production.

Uses the default credential chain (ECS task role). It never creates queues
and never accepts a generic HTTP/SQS execute helper.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from merchantos_domain import QueueMessage

from merchantos_queue.received import ReceivedMessage


class AwsSqsQueue:
    """Typed SQS client bound to one pre-created queue URL or name."""

    def __init__(
        self,
        *,
        queue_name: str,
        region: str,
        queue_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._queue_name = queue_name
        self._queue_url = queue_url
        self._client = client or boto3.client(
            "sqs",
            region_name=region,
            config=Config(retries={"max_attempts": 3}),
        )

    def ping(self) -> None:
        try:
            self._client.get_queue_url(QueueName=self._queue_name)
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("SQS is unreachable") from exc

    def enqueue(self, message: QueueMessage) -> None:
        dumped = message.model_dump(mode="json", exclude_none=True)
        if "merchant_id" in dumped or "store_id" in dumped:
            raise ValueError("queue messages must not carry tenant ids")
        self._client.send_message(
            QueueUrl=self._url(),
            MessageBody=message.model_dump_json(exclude_none=True),
        )

    def receive(
        self,
        *,
        max_messages: int = 1,
        wait_seconds: int = 0,
        visibility_timeout: int = 60,
    ) -> list[ReceivedMessage]:
        response = self._client.receive_message(
            QueueUrl=self._url(),
            MaxNumberOfMessages=min(max_messages, 10),
            WaitTimeSeconds=min(wait_seconds, 20),
            VisibilityTimeout=visibility_timeout,
        )
        received: list[ReceivedMessage] = []
        for raw in response.get("Messages") or []:
            body = raw.get("Body")
            handle = raw.get("ReceiptHandle")
            if not isinstance(body, str) or not isinstance(handle, str):
                continue
            received.append(
                ReceivedMessage(
                    message=QueueMessage.model_validate_json(body),
                    receipt_handle=handle,
                )
            )
        return received

    def delete(self, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=self._url(), ReceiptHandle=receipt_handle)

    def nack(self, receipt_handle: str) -> None:
        self._client.change_message_visibility(
            QueueUrl=self._url(),
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=0,
        )

    def _url(self) -> str:
        if self._queue_url:
            return self._queue_url
        response = self._client.get_queue_url(QueueName=self._queue_name)
        self._queue_url = str(response["QueueUrl"])
        return self._queue_url
