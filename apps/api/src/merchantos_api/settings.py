from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_name: str = "merchantos"
    log_level: str = "INFO"
    web_origin: str = "http://localhost:3000"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql://merchantos:merchantos@localhost:5432/merchantos"
    redis_url: str = "redis://localhost:6379/0"
    sqs_endpoint_url: str | None = None
    sqs_region: str = "us-east-1"
    sqs_queue_name: str = "merchantos-dev-jobs"
    aws_access_key_id: str = Field(default="local")
    aws_secret_access_key: str = Field(default="local")


def get_settings() -> Settings:
    return Settings()
