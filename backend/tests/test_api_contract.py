"""Contract tests for API v1 endpoints validating frontend contract alignment."""

import pytest
import httpx
from unittest.mock import AsyncMock
from evidence_ocr.api.dependencies import get_document_repository
from evidence_ocr.models.document import DocumentEntity, DocumentStatus


@pytest.fixture
def mock_doc_repo():
    repo = AsyncMock()
    doc = DocumentEntity(
        id="demo-1",
        name="Field notes — site inspection",
        kind="Field notes",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="Sample document",
        size="Illustrative source",
        sample=True,
        revision=1,
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )
    repo.get_by_id.return_value = doc
    repo.list_documents.return_value = ([doc], 1)
    repo.increment_revision.return_value = doc.model_copy(update={"revision": 2})
    return repo


@pytest.mark.asyncio
async def test_list_documents_contract(app, client: httpx.AsyncClient, mock_doc_repo):
    """GET /api/v1/documents matches expected schema."""
    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    try:
        response = await client.get("/api/v1/documents")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == "demo-1"
        assert item["name"] == "Field notes — site inspection"
        assert item["status"] == "Needs review"
    finally:
        app.dependency_overrides.pop(get_document_repository, None)


@pytest.mark.asyncio
async def test_evaluations_endpoint_contract(client: httpx.AsyncClient):
    """GET /api/v1/evaluations returns benchmark runs with hashes."""
    response = await client.get("/api/v1/evaluations")
    assert response.status_code == 200
    data = response.json()
    assert "runs" in data
    assert data["total"] >= 2
    assert "dataset_hash" in data["runs"][0]


@pytest.mark.asyncio
async def test_review_session_contract(app, client: httpx.AsyncClient, mock_doc_repo):
    """GET /api/v1/documents/{id}/review returns transcript, regions, and revision."""
    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    try:
        response = await client.get("/api/v1/documents/demo-1/review")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "demo-1"
        assert "Site inspection" in data["transcript"]
        assert len(data["regions"]) == 3
        assert data["revision"] == 1
    finally:
        app.dependency_overrides.pop(get_document_repository, None)


@pytest.mark.asyncio
async def test_patch_region_decision_contract(app, client: httpx.AsyncClient, mock_doc_repo):
    """PATCH /api/v1/documents/{id}/regions/{regionId} updates decision with concurrency revision."""
    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    try:
        response = await client.patch(
            "/api/v1/documents/demo-1/regions/r1",
            json={
                "decision": "4.8",
                "is_illegible": False,
                "expected_revision": 1,
                "reviewer": "Sanjit",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"]["id"] == "r1"
        assert data["region"]["decision"] == "4.8"
        assert data["revision"] == 2
        assert "audit_event" in data
    finally:
        app.dependency_overrides.pop(get_document_repository, None)


@pytest.mark.asyncio
async def test_complete_review_rejects_unresolved_regions(app, client: httpx.AsyncClient, mock_doc_repo):
    """POST /api/v1/documents/{id}/complete rejects if mandatory regions are unresolved."""
    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    try:
        # Regions r2 and r3 are still pending
        response = await client.post(
            "/api/v1/documents/demo-1/complete",
            json={"expected_revision": 1, "reviewer": "Sanjit"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "unresolved" in data["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_document_repository, None)
