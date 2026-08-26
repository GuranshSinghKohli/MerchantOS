from functools import lru_cache

from merchantos_db import create_db_engine
from merchantos_queue import QueuePort, create_queue
from redis import Redis
from sqlalchemy import Engine

from merchantos_api.settings import Settings, get_settings


@lru_cache
def settings() -> Settings:
    return get_settings()


@lru_cache
def db_engine() -> Engine:
    return create_db_engine(settings().database_url)


@lru_cache
def redis_client() -> Redis:
    return Redis.from_url(settings().redis_url, decode_responses=True)


@lru_cache
def queue() -> QueuePort:
    cfg = settings()
    return create_queue(
        endpoint_url=cfg.sqs_endpoint_url,
        queue_name=cfg.sqs_queue_name,
        region=cfg.sqs_region,
        access_key_id=cfg.aws_access_key_id,
        secret_access_key=cfg.aws_secret_access_key,
        environment=cfg.app_env,
    )
