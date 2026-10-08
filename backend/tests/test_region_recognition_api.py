"""API contract tests for region handwriting recognition endpoints."""

from unittest.mock import AsyncMock, patch
import httpx
import pytest

from evidence_ocr.api.dependencies import get_document_repository, get_ocr_provider
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.models.region import BoundingBox
from evidence_ocr.providers.ocr import BaseOCRProvider, OCRResult, OCRWord, ProviderMetadata


class StubOCRProvider(BaseOCRProvider):
    """Deterministic fast provider for contract testing."""

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name="trocr",
            model_identifier="microsoft/trocr-base-handwritten",
            model_version="base-handwritten-v1.0",
            parameters={"device": "cpu"},
        )

    async def recognize_page(self, image_bytes: bytes, language_hint=None) -> OCRResult:
        return OCRResult(
            raw_text="The north wall measures 4.8 metres.",
            words=[
                OCRWord(
                    text="The",
                    confidence=0.96,
                    bounding_box={"x": 0.0, "y": 0.0, "w": 10.0, "h": 100.0},
                )
            ],
            metadata=self.get_metadata(),
            execution_time_ms=45.2,
        )


@pytest.fixture
def mock_sample_doc():
    return DocumentEntity(
        id="demo-1",
        document_id="demo-1",
        name="Field notes — site inspection",
        kind="Field notes",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="Sample document",
        size="1.0 MB",
        sample=True,
        source_url="http://test/file",
        revision=1,
        sha256="abc123",
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_recognize_region_demo_document(app, client: httpx.AsyncClient, mock_sample_doc):
    """POST /documents/{id}/regions/{regionId}/recognize returns candidate suggestion with model metadata."""
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_sample_doc

    app.dependency_overrides[get_document_repository] = lambda: mock_repo
    app.dependency_overrides[get_ocr_provider] = lambda: StubOCRProvider()

    try:
        response = await client.post(
            "/api/v1/documents/demo-1/regions/r1/recognize",
            json={
                "bounding_box": {"x": 10.0, "y": 10.0, "w": 80.0, "h": 10.0},
                "page_index": 0,
            },
        )
        assert response.status_code == 200
        data = response.json()

        assert data["document_id"] == "demo-1"
        assert data["region_id"] == "r1"
        assert len(data["recognized_text"]) > 0
        assert data["confidence"] > 0.0
        assert data["model_identifier"] == "microsoft/trocr-base-handwritten"
        assert data["is_verified"] is False
        assert data["candidate"]["provider_id"] == "trocr"
        assert data["candidate"]["model_version"] == "base-handwritten-v1.0"
    finally:
        app.dependency_overrides.pop(get_document_repository, None)
        app.dependency_overrides.pop(get_ocr_provider, None)


@pytest.mark.asyncio
async def test_recognize_region_invalid_bounding_box(app, client: httpx.AsyncClient, mock_sample_doc):
    """POST /documents/{id}/regions/{regionId}/recognize rejects invalid bounding box coordinates exceeding 100%."""
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_sample_doc
    app.dependency_overrides[get_document_repository] = lambda: mock_repo
    try:
        response = await client.post(
            "/api/v1/documents/demo-1/regions/r1/recognize",
            json={
                "bounding_box": {"x": 80.0, "y": 10.0, "w": 30.0, "h": 10.0},  # 80 + 30 = 110 > 100
                "page_index": 0,
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_document_repository, None)
