"""Tests for middleware: correlation IDs, timing, security headers, and error formatting."""

import pytest
import httpx


@pytest.mark.asyncio
async def test_request_id_generated_and_propagated(client: httpx.AsyncClient):
    """Verify X-Request-ID is generated and returned in headers."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"].startswith("req-")
    assert "x-response-time-ms" in response.headers


@pytest.mark.asyncio
async def test_custom_request_id_preserved(client: httpx.AsyncClient):
    """Verify client-supplied X-Request-ID is preserved."""
    custom_id = "test-correlation-12345"
    response = await client.get("/api/v1/health/live", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_security_headers_present(client: httpx.AsyncClient):
    """Verify security headers are applied."""
    response = await client.get("/api/v1/health/live")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
async def test_not_found_returns_standard_error_envelope(app, client: httpx.AsyncClient):
    """Verify 404 routes or missing entities return standardized error envelope."""
    from unittest.mock import AsyncMock
    from evidence_ocr.api.dependencies import get_job_repository

    mock_job_repo = AsyncMock()
    mock_job_repo.get_by_id.return_value = None
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo
    try:
        response = await client.get("/api/v1/jobs/nonexistent-job-id")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert "nonexistent-job-id" in data["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_job_repository, None)
