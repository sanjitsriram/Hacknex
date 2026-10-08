"""Contract tests for document-level recognition scheduling, regions retrieval, and jobs history."""

from unittest.mock import AsyncMock
import httpx
import pytest

from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_job_repository,
    get_region_repository,
    get_worker_runner,
)
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.models.region import BoundingBox, RegionEntity, RegionReviewStatus


@pytest.fixture
def sample_doc():
    return DocumentEntity(
        id="doc-test-1",
        document_id="doc-test-1",
        name="Contract notes",
        kind="Legal",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="Today",
        size="500 KB",
        sample=False,
        revision=1,
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )


@pytest.mark.asyncio
async def test_schedule_recognition_creates_job(app, client: httpx.AsyncClient, sample_doc):
    """POST /documents/{id}/recognition enqueues a new PP-OCRv6 recognition job."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_job_repo = AsyncMock()
    mock_job_repo.find_active_by_document.return_value = None
    mock_job_repo.create = AsyncMock()

    mock_runner = AsyncMock()
    mock_runner.dispatch_document_recognition = AsyncMock()

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo
    app.dependency_overrides[get_worker_runner] = lambda: mock_runner

    try:
        resp = await client.post(
            "/api/v1/documents/doc-test-1/recognition",
            json={"pipeline_version": "v1.0.0"},
        )
        assert resp.status_code == 202
        data = resp.json()

        assert data["document_id"] == "doc-test-1"
        assert data["status"] == "queued"
        assert data["stage"] == "ingestion"
        assert data["provider"] == "paddleocr-cloud"
        assert data["model"] == "PP-OCRv6"
        assert mock_job_repo.create.called
        assert mock_runner.dispatch_document_recognition.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_schedule_recognition_deduplicates_active_job(app, client: httpx.AsyncClient, sample_doc):
    """POST /documents/{id}/recognition returns active job if one is already running."""
    active_job = ProcessingJob(
        id="job-existing-1",
        document_id="doc-test-1",
        pipeline_version="v1.0.0",
        status=JobStatus.RUNNING,
        stage=JobStage.RECOGNITION,
        provider="paddleocr-cloud",
        model="PP-OCRv6",
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_job_repo = AsyncMock()
    mock_job_repo.find_active_by_document.return_value = active_job
    mock_job_repo.create = AsyncMock()

    mock_runner = AsyncMock()

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo
    app.dependency_overrides[get_worker_runner] = lambda: mock_runner

    try:
        resp = await client.post(
            "/api/v1/documents/doc-test-1/recognition",
            json={"pipeline_version": "v1.0.0"},
        )
        assert resp.status_code == 202
        data = resp.json()

        assert data["job_id"] == "job-existing-1"
        assert data["status"] == "running"
        # Verify no second job was created
        assert not mock_job_repo.create.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_regions(app, client: httpx.AsyncClient, sample_doc):
    """GET /documents/{id}/regions returns detected regions with polygons and coordinates."""
    mock_region = RegionEntity(
        id="r1",
        document_id="doc-test-1",
        page_index=0,
        line="The north wall measures 4.8 metres.",
        original="The north wall measures 4.8 metres.",
        bounding_box=BoundingBox(x=10.0, y=20.0, w=50.0, h=10.0),
        polygon=[[100, 200], [600, 200], [600, 300], [100, 300]],
        confidence=0.952,
        provider_id="paddleocr-cloud",
        model_version="PP-OCRv6",
        reason="Initial cloud detection",
        status=RegionReviewStatus.PENDING,
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_region_repo = AsyncMock()
    mock_region_repo.get_by_document_id.return_value = [mock_region]

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_region_repository] = lambda: mock_region_repo

    try:
        resp = await client.get("/api/v1/documents/doc-test-1/regions")
        assert resp.status_code == 200
        data = resp.json()

        assert data["document_id"] == "doc-test-1"
        assert data["total"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["id"] == "r1"
        assert item["original"] == "The north wall measures 4.8 metres."
        assert item["confidence"] == 0.952
        assert item["provider_id"] == "paddleocr-cloud"
        assert item["bounding_box"] == {"x": 10.0, "y": 20.0, "w": 50.0, "h": 10.0}
        assert item["polygon"] == [[100, 200], [600, 200], [600, 300], [100, 300]]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_document_jobs(app, client: httpx.AsyncClient, sample_doc):
    """GET /documents/{id}/jobs returns list of all jobs for the document."""
    job1 = ProcessingJob(
        id="job-1",
        document_id="doc-test-1",
        pipeline_version="v1.0.0",
        status=JobStatus.COMPLETED,
        stage=JobStage.COMPLETED,
        provider="paddleocr-cloud",
        model="PP-OCRv6",
        execution_time_ms=1850.5,
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:02Z",
    )

    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_job_repo = AsyncMock()
    mock_job_repo.list_by_document.return_value = [job1]

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_job_repository] = lambda: mock_job_repo

    try:
        resp = await client.get("/api/v1/documents/doc-test-1/jobs")
        assert resp.status_code == 200
        data = resp.json()

        assert len(data) == 1
        assert data[0]["job_id"] == "job-1"
        assert data[0]["status"] == "completed"
        assert data[0]["provider"] == "paddleocr-cloud"
        assert data[0]["model"] == "PP-OCRv6"
        assert data[0]["execution_time_ms"] == 1850.5
    finally:
        app.dependency_overrides.clear()
