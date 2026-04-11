from __future__ import annotations
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    aws_default_region: str      = "eu-west-2"
    aws_endpoint_url:   str | None = None

    dynamodb_table: str = "codelens-jobs-dev"
    sqs_queue_url:  str = ""
    s3_bucket:      str = "codelens-storage-dev"

    openai_api_key: str      = ""
    voyage_api_key: str      = ""
    qdrant_url:     str      = "http://localhost:6333"
    qdrant_api_key: str | None = None

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
