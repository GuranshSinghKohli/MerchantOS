from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql://merchantos:merchantos@localhost:5432/merchantos"
    redis_url: str | None = None
    sqs_endpoint_url: str | None = None
    sqs_region: str = "us-east-1"
    sqs_queue_name: str = "merchantos-dev-jobs"
    sqs_queue_url: str | None = None
    aws_access_key_id: str = Field(default="local")
    aws_secret_access_key: str = Field(default="local")
    worker_once: bool = False
    shopify_api_key: str = ""
    shopify_api_secret: str = ""
    token_encryption_key: str = ""
    token_encryption_key_version: str = "local-v1"
    llm_provider: str = "fake"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
