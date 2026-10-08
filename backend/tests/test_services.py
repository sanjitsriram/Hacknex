"""Tests for domain services: ingestion, review with optimistic concurrency, and evaluations."""

import pytest
from unittest.mock import AsyncMock
from evidence_ocr.core.errors import InvalidInputError, PreconditionFailedError
from evidence_ocr.evaluation.service import EvaluationService
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.ingestion.validator import validate_document_upload
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.providers.storage import MockStorageProvider
from evidence_ocr.review.service import ReviewService


def test_validate_document_upload_rules():
    """Verify document upload constraints."""
    allowed = ["image/png", "image/jpeg", "application/pdf"]
    max_bytes = 20 * 1024 * 1024

    # Empty file
    with pytest.raises(InvalidInputError, match="empty"):
        validate_document_upload("test.png", "image/png", 0, allowed, max_bytes)

    # Oversized file
    with pytest.raises(InvalidInputError, match="maximum file size"):
        validate_document_upload("test.png", "image/png", 25 * 1024 * 1024, allowed, max_bytes)

    # Unsupported MIME
    with pytest.raises(InvalidInputError, match="unsupported file type"):
        validate_document_upload("test.exe", "application/x-msdownload", 100, allowed, max_bytes)


@pytest.mark.asyncio
async def test_review_service_optimistic_concurrency():
    """Verify ReviewService enforces revision checking and increments on update."""
    mock_repo = AsyncMock()
    doc_initial = DocumentEntity(
        id="doc-test-1",
        name="Test Document",
        kind="Field notes",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="2026-10-08T12:00:00Z",
        size="12.0 KB",
        revision=1,
        created_at="2026-10-08T12:00:00Z",
        updated_at="2026-10-08T12:00:00Z",
    )
    doc_updated = doc_initial.model_copy(update={"revision": 2})

    mock_repo.get_by_id.return_value = doc_initial
    mock_repo.increment_revision.return_value = doc_updated

    review_service = ReviewService(document_repo=mock_repo)

    # Valid revision update
    res = await review_service.update_region_decision(
        document_id="doc-test-1",
        region_id="r1",
        decision="4.8",
        is_illegible=False,
        expected_revision=1,
    )
    assert res.revision == 2
    assert res.audit_event.action == "Accepted alternative"

    # Simulated revision mismatch error
    mock_repo.increment_revision.side_effect = PreconditionFailedError(
        "Revision mismatch", expected_revision=1, actual_revision=2
    )
    with pytest.raises(PreconditionFailedError):
        await review_service.update_region_decision(
            document_id="doc-test-1",
            region_id="r1",
            decision="4.8",
            is_illegible=False,
            expected_revision=1,
        )


@pytest.mark.asyncio
async def test_evaluation_service_returns_verifiable_metrics():
    """Verify evaluation service returns runs with reproducible dataset hashes and denominators."""
    eval_svc = EvaluationService()
    res = await eval_svc.list_evaluations()
    assert res.total >= 2
    for run in res.runs:
        assert run.denominator > 0
        assert len(run.dataset_hash) == 64  # SHA-256
        assert run.is_demo is False
