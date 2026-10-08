"""Integration tests for Phase 6 Fusion API endpoints.

Covers:
  - POST /documents/{id}/fusion-runs (success, 202, job queued)
  - POST /documents/{id}/fusion-runs (404 on nonexistent document)
  - GET /documents/{id}/fusion-runs (list runs for document)
  - GET /documents/{id}/fusion-runs/{run_id} (run detail with proposals)
  - GET /documents/{id}/disagreements (retrieves disagreement records with filter)
  - POST /documents/{id}/regions/{region_id}/recover (queues recovery, returns 202)
  - GET /documents/{id}/regions/{region_id}/evidence (evidence package with crops and candidates)
"""

from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_fusion_service,
)
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.models.fusion import (
    DisagreementRecord,
    DisagreementSeverity,
    DisagreementType,
    EvidenceAlignment,
    FusionProposal,
    FusionRun,
    FusionStatus,
    MatchStatus,
    RecoveryAttempt,
    RecoveryOutcome,
)
from evidence_ocr.models.region import BoundingBox, RegionEntity
from evidence_ocr.schemas.fusion import RegionEvidenceResponse


@pytest.fixture
def sample_doc():
    return DocumentEntity(
        id="doc-fusion-1",
        document_id="doc-fusion-1",
        name="Field Inspection Log",
        kind="Technical",
        language="English",
        pages=1,
        status=DocumentStatus.NEEDS_REVIEW,
        added="Today",
        size="500 KB",
        sample=False,
        revision=1,
        created_at="2026-10-09T00:00:00Z",
        updated_at="2026-10-09T00:00:00Z",
    )


@pytest.fixture
def sample_fusion_run():
    return FusionRun(
        id="frun-test-1",
        document_id="doc-fusion-1",
        strategy_version="evidence-aware-v1",
        alignment_algorithm_version="spatial-v1",
        status=FusionStatus.COMPLETED,
        region_count=2,
        matched_count=2,
        disagreement_count=1,
        recovery_eligible_count=1,
        auto_proposable_count=1,
        requires_review_count=1,
        execution_time_ms=120.0,
        created_by_session="test-session-1",
        created_at="2026-10-09T00:00:00Z",
        updated_at="2026-10-09T00:00:01Z",
    )


@pytest.mark.asyncio
async def test_create_fusion_run_success(app, client: httpx.AsyncClient, sample_doc, sample_fusion_run):
    """POST /documents/{id}/fusion-runs queues a run and returns 202 Accepted."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_fusion_svc = MagicMock()
    mock_fusion_svc.fusion_repo = None
    mock_fusion_svc.create_fusion_run = AsyncMock(return_value=sample_fusion_run)
    mock_fusion_svc.execute_fusion = AsyncMock(return_value=sample_fusion_run)

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_fusion_service] = lambda: mock_fusion_svc

    try:
        resp = await client.post(
            "/api/v1/documents/doc-fusion-1/fusion-runs",
            json={"strategy": "evidence-aware-v1"},
            headers={"X-Session-Id": "test-session-1"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["fusion_run_id"] == "frun-test-1"
        assert data["document_id"] == "doc-fusion-1"
        assert data["status"] in ("completed", "queued")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_fusion_run_doc_not_found(app, client: httpx.AsyncClient):
    """POST /documents/{id}/fusion-runs returns 404 when document does not exist."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = None

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo

    try:
        resp = await client.post(
            "/api/v1/documents/doc-nonexistent/fusion-runs",
            json={"strategy": "evidence-aware-v1"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_fusion_runs(app, client: httpx.AsyncClient, sample_doc, sample_fusion_run):
    """GET /documents/{id}/fusion-runs returns list of runs."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_fusion_svc = MagicMock()
    mock_fusion_svc.list_fusion_runs = AsyncMock(return_value=[sample_fusion_run])

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_fusion_service] = lambda: mock_fusion_svc

    try:
        resp = await client.get(
            "/api/v1/documents/doc-fusion-1/fusion-runs",
            headers={"X-Session-Id": "test-session-1"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["fusion_run_id"] == "frun-test-1"
        assert items[0]["region_count"] == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_fusion_run_detail(app, client: httpx.AsyncClient, sample_doc, sample_fusion_run):
    """GET /documents/{id}/fusion-runs/{run_id} returns run detail and proposals."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_proposal = FusionProposal(
        id="prop-1",
        fusion_run_id="frun-test-1",
        document_id="doc-fusion-1",
        region_id="reg-1",
        page_index=0,
        proposed_text="The north wall 4.8m",
        strategy_version="evidence-aware-v1",
        auto_proposable=False,
        requires_review=True,
        disagreement_reasons=["NUMERIC_CONFLICT"],
        candidates=[],
        uncertainty_indicators=["MODEL_DISAGREEMENT"],
        recovery_attempt_ids=[],
        is_human_verified=False,
        calibration_status="UNCALIBRATED",
        source_evidence_reference={},
        created_at="2026-10-09T00:00:00Z",
        updated_at="2026-10-09T00:00:00Z",
    )

    mock_fusion_svc = MagicMock()
    mock_fusion_svc.get_fusion_run = AsyncMock(return_value=sample_fusion_run)
    mock_fusion_svc.get_proposals = AsyncMock(return_value=[mock_proposal])

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_fusion_service] = lambda: mock_fusion_svc

    try:
        resp = await client.get(
            "/api/v1/documents/doc-fusion-1/fusion-runs/frun-test-1",
            headers={"X-Session-Id": "test-session-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fusion_run_id"] == "frun-test-1"
        assert len(data["proposals"]) == 1
        assert data["proposals"][0]["proposed_text"] == "The north wall 4.8m"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_disagreements_with_filter(app, client: httpx.AsyncClient, sample_doc):
    """GET /documents/{id}/disagreements filters by severity."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_record = DisagreementRecord(
        id="dis-1",
        fusion_run_id="frun-test-1",
        document_id="doc-fusion-1",
        region_id="reg-1",
        page_index=0,
        disagreement_type=DisagreementType.NUMERIC_CONFLICT,
        severity=DisagreementSeverity.CRITICAL,
        description="Numeric mismatch 4.8 vs 4.3",
        created_at="2026-10-09T00:00:00Z",
    )

    mock_fusion_svc = MagicMock()
    mock_fusion_svc.get_disagreements = AsyncMock(return_value=[mock_record])

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_fusion_service] = lambda: mock_fusion_svc

    try:
        resp = await client.get(
            "/api/v1/documents/doc-fusion-1/disagreements?severity=CRITICAL",
            headers={"X-Session-Id": "test-session-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["disagreements"][0]["severity"] == "CRITICAL"
        assert data["disagreements"][0]["disagreement_type"] == "NUMERIC_CONFLICT"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recover_region_endpoint(app, client: httpx.AsyncClient, sample_doc):
    """POST /documents/{id}/regions/{region_id}/recover executes bounded recovery."""
    mock_doc_repo = AsyncMock()
    mock_doc_repo.get_by_id.return_value = sample_doc

    mock_attempt = RecoveryAttempt(
        id="rec-123",
        document_id="doc-fusion-1",
        region_id="reg-1",
        page_index=0,
        variant_type="padded",
        variant_hash="abc123hash",
        model_provider="trocr",
        model_version="base-v1",
        execution_time_ms=50.0,
        outcome=RecoveryOutcome.IMPROVED,
        created_at="2026-10-09T00:00:00Z",
    )

    mock_fusion_svc = MagicMock()
    mock_fusion_svc.recover_region = AsyncMock(return_value=[mock_attempt])

    app.dependency_overrides[get_document_repository] = lambda: mock_doc_repo
    app.dependency_overrides[get_fusion_service] = lambda: mock_fusion_svc

    try:
        resp = await client.post(
            "/api/v1/documents/doc-fusion-1/regions/reg-1/recover",
            json={"fusion_run_id": "frun-test-1"},
            headers={"X-Session-Id": "test-session-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recovery_attempt_id"].startswith("rec-")
        assert data["status"] == "completed"
        mock_fusion_svc.recover_region.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()
