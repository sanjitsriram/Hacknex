"""Pytest fixtures for testing EvidenceOCR backend."""

import pytest
import httpx
from evidence_ocr.core.config import Settings
from evidence_ocr.main import create_app
from evidence_ocr.db.client import get_db_manager


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated testing settings."""
    return Settings(
        environment="testing",
        debug=True,
        mongodb_uri="mongodb://localhost:27017",
        mongodb_db_name="evidence_ocr_test",
        cors_origins=["http://localhost:3000"],
        log_level="DEBUG",
        log_format="console",
    )


@pytest.fixture
def app(test_settings: Settings):
    """Create test application instance."""
    return create_app(test_settings)


@pytest.fixture
async def client(app) -> httpx.AsyncClient:
    """Async HTTP test client bound to test app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
