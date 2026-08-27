import time
from uuid import uuid4

from merchantos_app import AnalyticsService
from merchantos_db import create_db_engine, ping_database
from merchantos_llm import FakeLLM, OpenAIAdapter, default_orchestrator_turns
from merchantos_mcp import build_commerce_registry
from merchantos_observability import configure_logging, get_logger
from merchantos_queue import create_queue
from merchantos_shopify.adapter import ShopifyAdapter
from merchantos_shopify.encryption import TokenEncryptor
from merchantos_shopify.mutator import AdapterShopifyMutator
from redis import Redis

from merchantos_worker import __version__
from merchantos_worker.capabilities import (
    AgentCapabilities,
    ExecutionCapabilities,
    SyncCapabilities,
    WebhookCapabilities,
    WorkerRuntime,
)
from merchantos_worker.dispatch import process_once
from merchantos_worker.settings import WorkerSettings


def build_runtime(settings: WorkerSettings) -> WorkerRuntime:
    engine = create_db_engine(settings.database_url)
    ping_database(engine)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    if redis_client.ping() is not True:
        raise RuntimeError("Redis ping failed")
    queue = create_queue(
        endpoint_url=settings.sqs_endpoint_url,
        queue_name=settings.sqs_queue_name,
        region=settings.sqs_region,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=settings.aws_secret_access_key,
        environment=settings.app_env,
        queue_url=settings.sqs_queue_url,
    )
    queue.ping()
    reader = ShopifyAdapter(
        client_id=settings.shopify_api_key or "worker",
        client_secret=settings.shopify_api_secret or "worker",
    )
    encryptor = None
    if settings.token_encryption_key:
        encryptor = TokenEncryptor.from_urlsafe_key(
            settings.token_encryption_key, settings.token_encryption_key_version
        )
    llm: FakeLLM | OpenAIAdapter
    if settings.openai_api_key and settings.llm_provider == "openai":
        llm = OpenAIAdapter(api_key=settings.openai_api_key, model=settings.openai_model)
    else:
        llm = FakeLLM(default_orchestrator_turns())
    return WorkerRuntime(
        engine=engine,
        queue=queue,
        sync=SyncCapabilities(reader=reader),
        webhook=WebhookCapabilities(reader=reader),
        agent=AgentCapabilities(
            tools=build_commerce_registry(AnalyticsService(engine)),
            llm=llm,
        ),
        execution=ExecutionCapabilities(mutator=AdapterShopifyMutator(reader)),
        encryptor=encryptor,
        owner=f"worker-{uuid4()}",
    )


def check_dependencies(settings: WorkerSettings) -> WorkerRuntime:
    return build_runtime(settings)


def run() -> None:
    settings = WorkerSettings()
    configure_logging(level=settings.log_level)
    logger = get_logger(__name__)
    runtime = build_runtime(settings)
    logger.info(
        "worker_started",
        env=settings.app_env,
        version=__version__,
        handler="sync_webhook",
        queue_type=type(runtime.queue).__name__,
    )
    if settings.worker_once:
        process_once(runtime)
        return
    while True:
        process_once(runtime, wait_seconds=2)
        time.sleep(1)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
