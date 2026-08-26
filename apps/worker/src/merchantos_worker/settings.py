from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql://merchantos:merchantos@localhost:5432/merchantos"
    redis_url: str = "redis://localhost:6379/0"
    sqs_endpoint_url: str | None = None
    sqs_region: str = "us-east-1"
    sqs_queue_name: str = "merchantos-dev-jobs"
    aws_access_key_id: str = Field(default="local")
    aws_secret_access_key: str = Field(default="local")
    worker_once: bool = False
