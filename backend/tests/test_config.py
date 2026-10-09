"""Tests for application settings and configuration loading."""

import pytest
from evidence_ocr.core.config import BACKEND_ENV_FILE, Settings


def test_settings_default_values():
    """Verify standard default settings values."""
    settings = Settings(_env_file=None)
    assert settings.app_name == "EvidenceOCR Backend"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.max_upload_size_bytes == 20 * 1024 * 1024
    assert settings.gridfs_bucket_name == "evidence_files"
    assert settings.max_pdf_pages == 20
    assert "image/png" in settings.allowed_mime_types
    assert "application/pdf" in settings.allowed_mime_types
    assert BACKEND_ENV_FILE.name == ".env"
    assert BACKEND_ENV_FILE.parent.name == "backend"


def test_settings_parse_cors_origins_json_and_csv():
    """Verify CORS origins parsing from JSON string and comma-separated string."""
    s1 = Settings(cors_origins='["https://evidence.app", "https://preview.app"]')
    assert s1.cors_origins == ["https://evidence.app", "https://preview.app"]

    s2 = Settings(cors_origins="https://evidence.app, https://preview.app")
    assert s2.cors_origins == ["https://evidence.app", "https://preview.app"]


def test_settings_parse_allowed_mimes():
    """Verify allowed MIME types parsing from string."""
    s = Settings(allowed_mime_types='["image/png", "image/jpeg"]')
    assert s.allowed_mime_types == ["image/png", "image/jpeg"]
