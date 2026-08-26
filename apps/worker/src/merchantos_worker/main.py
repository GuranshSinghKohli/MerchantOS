import time

from merchantos_db import create_db_engine, ping_database
from merchantos_observability import configure_logging, get_logger
from merchantos_queue import create_queue
from redis import Redis

from merchantos_worker import __version__
from merchantos_worker.capabilities import IdleWorkerCapabilities
from merchantos_worker.settings import WorkerSettings


def check_dependencies(settings: WorkerSettings) -> IdleWorkerCapabilities:
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
    )
    queue.ping()
    return IdleWorkerCapabilities(queue=queue)


def run() -> None:
    settings = WorkerSettings()
    configure_logging(level=settings.log_level)
    logger = get_logger(__name__)
    capabilities = check_dependencies(settings)
    logger.info(
        "worker_started",
        env=settings.app_env,
        version=__version__,
        handler="idle",
        queue_type=type(capabilities.queue).__name__,
    )
    if settings.worker_once:
        return
    while True:
        time.sleep(30)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
