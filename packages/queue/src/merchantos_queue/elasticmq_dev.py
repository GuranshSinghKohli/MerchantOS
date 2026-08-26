"""DEVELOPMENT ONLY.

Talks to local ElasticMQ using dummy AWS keys. Do not use this adapter in
staging or production — those environments use AWS SQS via a future adapter.
"""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from merchantos_domain import QueueMessage


class ElasticMqDevQueue:
    """SQS-compatible client bound to a local ElasticMQ endpoint."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        queue_name: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        if "amazonaws.com" in endpoint_url:
            raise ValueError("ElasticMqDevQueue refuses production AWS endpoints")
        self._queue_name = queue_name
        self._client: Any = boto3.client(
            "sqs",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(retries={"max_attempts": 2}),
        )
        self._queue_url: str | None = None

    def ping(self) -> None:
        try:
            self._client.list_queues()
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError("ElasticMQ is unreachable") from exc

    def enqueue(self, message: QueueMessage) -> None:
        dumped = message.model_dump(mode="json", exclude_none=True)
        if "merchant_id" in dumped or "store_id" in dumped:
            raise ValueError("queue messages must not carry tenant ids")
        self._client.send_message(
            QueueUrl=self._ensure_queue(),
            MessageBody=message.model_dump_json(exclude_none=True),
        )

    def _ensure_queue(self) -> str:
        if self._queue_url is not None:
            return self._queue_url
        response = self._client.create_queue(QueueName=self._queue_name)
        self._queue_url = str(response["QueueUrl"])
        return self._queue_url
