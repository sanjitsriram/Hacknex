"""Contract tests for PaddleOCR-VL document intelligence endpoints."""

from unittest.mock import AsyncMock
import httpx
import pytest

from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_job_repository,
    get_parsing_repository,
    get_worker_runner,
)
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.models.parsing import DocumentParsingRun, LayoutBlock, ParsedPage
from evidence_ocr.models.region import BoundingBox


@pytest.fixture
def sample_doc():
    return DocumentEntity(
        id="doc-test-vl-1",
        document_id="doc-test-vl-1",
        name="Engineering Blueprint Notes",
        kind="Technical",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="Today",
        size="750 KB",
        sample=False,
        revision=1,
        created_at="2026-10-09T00:00:00Z",
        updated_at="2026-10-09T00:00:00Z",
    )


@pytest.fixture
def sample_parsing_run():
    return DocumentParsingRun(
        id="run-vl-1234",
        document_id="doc-test-vl-1",
        job_id="job-vl-5678",
        provider_id="paddleocr-cloud",
        model_version="PaddleOCR-VL-1.6",
        provider_job_id="101756714305089536",
        page_count=1,
        markdown_text="# Engineering Blueprint Notes\n\n| Part | Tolerance |\n|---|---|\n| Beam A | 0.05 mm |",
        pages=[
            ParsedPage(
                page_index=0,
                width=1200,
                height=1600,
                markdown_text="# Engineering Blueprint Notes\n\n| Part | Tolerance |\n|---|---|\n| Beam A | 0.05 mm |",
                blocks=[
                    LayoutBlock(
                        block_id="blk-p0-001",
                        page_index=0,
                        block_type="paragraph_title",
                        bounding_box=BoundingBox(x=10.0, y=5.0, w=80.0, h=8.0),
                        content="# Engineering Blueprint Notes",
                        reading_order=1,
                        confidence=0.96,
                    ),
                    LayoutBlock(
                        block_id="blk-p0-002",
                        page_index=0,
                        block_type="table",
                        bounding_box=BoundingBox(x=10.0, y=15.0, w=80.0, h=30.0),
                        content="| Part | Tolerance |\n|---|---|\n| Beam A | 0.05 mm |",
                        reading_order=2,
                        confidence=0.92,
                    ),
                ],
                reading_order_sequence=["blk-p0-001", "blk-p0-002"],
                tables_count=1,
            )
        ],
        total_blocks=2,
        execution_time_ms=1840.0,
        created_at="2026-10-09T00:00:01Z",
    )


@pytest.mark.asyncio
async def test_schedule_document_intelligence_creates_job(app, client: httpx.AsyncClient, sample_doc):
    """POST /documents/{id}/document-intelligence creates a PaddleOCR-VL job."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_job_repo = AsyncMock()
    mock_job_repo.list_by_document.return_value = []
    mock_job_repo.create = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.dispatch_document_intelligence = AsyncMock()

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo
    app.dependency_overrides[get_worker_runner] = lambda: mock_runner

    try:
        resp = await client.post(
            "/api/v1/documents/doc-test-vl-1/document-intelligence",
            json={"pipeline_version": "v1.0.0"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["document_id"] == "doc-test-vl-1"
        assert data["model"] == "PaddleOCR-VL-1.6"
        assert data["provider"] == "paddleocr-cloud"
        assert data["status"] == "queued"
        mock_runner.dispatch_document_intelligence.assert_called_once()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_schedule_document_intelligence_deduplication(app, client: httpx.AsyncClient, sample_doc):
    """POST /documents/{id}/document-intelligence returns active job if already running."""
    active_job = ProcessingJob(
        id="job-existing-vl",
        document_id="doc-test-vl-1",
        task_type="document_intelligence",
        status=JobStatus.RUNNING,
        stage=JobStage.LAYOUT_INTELLIGENCE,
        provider="paddleocr-cloud",
        model="PaddleOCR-VL-1.6",
        created_at="2026-10-09T00:00:00Z",
        updated_at="2026-10-09T00:00:00Z",
    )

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_job_repo = AsyncMock()
    mock_job_repo.list_by_document.return_value = [active_job]

    mock_runner = AsyncMock()

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo
    app.dependency_overrides[get_worker_runner] = lambda: mock_runner

    try:
        resp = await client.post(
            "/api/v1/documents/doc-test-vl-1/document-intelligence",
            json={"pipeline_version": "v1.0.0"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == "job-existing-vl"
        assert data["status"] == "running"
        # Runner shouldn't be dispatched again
        mock_runner.dispatch_document_intelligence.assert_not_called()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_parsed_document_returns_run(app, client: httpx.AsyncClient, sample_doc, sample_parsing_run):
    """GET /documents/{id}/parsed-document returns structured layout blocks, reading orders, and Markdown."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_parsing_repo = AsyncMock()
    mock_parsing_repo.get_latest_by_document.return_value = sample_parsing_run

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_parsing_repository] = lambda: mock_parsing_repo

    try:
        resp = await client.get("/api/v1/documents/doc-test-vl-1/parsed-document")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "run-vl-1234"
        assert data["model_version"] == "PaddleOCR-VL-1.6"
        assert len(data["pages"]) == 1
        page0 = data["pages"][0]
        assert len(page0["blocks"]) == 2
        assert page0["reading_order_sequence"] == ["blk-p0-001", "blk-p0-002"]
        assert page0["tables_count"] == 1
        assert "Engineering Blueprint Notes" in data["markdown_text"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_parsing_history(app, client: httpx.AsyncClient, sample_doc, sample_parsing_run):
    """GET /documents/{id}/parsing-history returns list of parsing runs."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_parsing_repo = AsyncMock()
    mock_parsing_repo.list_by_document.return_value = [sample_parsing_run]

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_parsing_repository] = lambda: mock_parsing_repo

    try:
        resp = await client.get("/api/v1/documents/doc-test-vl-1/parsing-history")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "run-vl-1234"
    finally:
        app.dependency_overrides.clear()
