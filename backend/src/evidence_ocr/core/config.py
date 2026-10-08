"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """EvidenceOCR Backend Settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "EvidenceOCR Backend"
    environment: str = Field(default="development", description="development | staging | production | testing")
    debug: bool = Field(default=False, description="Enable debug mode")
    app_host: str = Field(default="0.0.0.0", description="Server bind host")
    app_port: int = Field(default=8000, description="Server bind port")
    api_v1_prefix: str = "/api/v1"

    # MongoDB Atlas (PyMongo Async)
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string (supports mongodb+srv:// for Atlas)",
    )
    mongodb_db_name: str = Field(default="evidence_ocr", description="Database name")
    mongodb_connect_timeout_ms: int = Field(default=3000, description="Connection timeout in ms")
    mongodb_server_selection_timeout_ms: int = Field(
        default=2000, description="Server selection timeout in ms for fast health check failure"
    )

    # Security & CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins for frontend client",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    log_format: str = Field(default="console", description="Format: console or json")

    # Document Ingestion & Storage (Phase 2 MongoDB GridFS)
    gridfs_bucket_name: str = Field(
        default="evidence_files", description="MongoDB GridFS bucket for original binary files"
    )
    max_upload_size_bytes: int = Field(
        default=10 * 1024 * 1024, description="Maximum allowed document file size (10 MiB default)"
    )
    max_pdf_pages: int = Field(
        default=20, description="Maximum allowed pages for uploaded PDF documents"
    )
    upload_timeout_seconds: int = Field(
        default=30, description="Document upload request timeout in seconds"
    )
    allowed_mime_types: List[str] = Field(
        default=["application/pdf", "image/png", "image/jpeg", "image/webp"],
        description="Allowed document MIME types",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("allowed_mime_types", mode="before")
    @classmethod
    def assemble_allowed_mimes(cls, v):
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [mime.strip() for mime in v.split(",") if mime.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
