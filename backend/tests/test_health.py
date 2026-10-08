"""Tests for liveness and readiness health endpoints."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch
from evidence_ocr.core.errors import DatabaseUnavailableError
from evidence_ocr.db.client import get_db_manager


@pytest.mark.asyncio
async def test_liveness_endpoint_returns_ok(client: httpx.AsyncClient):
    """GET /api/v1/health/live should always return 200 and alive status."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert "timestamp" in data
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_connected(client: httpx.AsyncClient):
    """GET /api/v1/health/ready should return 200 when database ping succeeds."""
    db_manager = get_db_manager()
    with patch.object(db_manager, "ping", new=AsyncMock(return_value=True)):
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_when_db_disconnected(client: httpx.AsyncClient):
    """GET /api/v1/health/ready should return 503 when database ping fails."""
    db_manager = get_db_manager()
    with patch.object(
        db_manager, "ping", new=AsyncMock(side_effect=DatabaseUnavailableError("Cluster unreachable"))
    ):
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"
        assert "Cluster unreachable" in data["error"]
