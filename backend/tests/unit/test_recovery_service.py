"""Unit tests for RecoveryService."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from evidence_ocr.fusion.recovery import RecoveryService
from evidence_ocr.models.fusion import (
    FusionProposal,
    RecoveryOutcome,
    RecoveryVariantType,
)
from evidence_ocr.models.region import BoundingBox, RegionEntity


def make_region(rid="r1", confidence=0.3, page=0):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return RegionEntity(
        id=rid, document_id="doc-1", page_index=page, line=str(page + 1),
        bounding_box=BoundingBox(x=10.0, y=10.0, w=20.0, h=5.0),
        original="test text", reason="",
        confidence=confidence,
        created_at=now, updated_at=now,
    )


def make_proposal(requires_review=True, indicators=None):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return FusionProposal(
        id="prop-001", fusion_run_id="frun-1", document_id="doc-1",
        region_id="r1", page_index=0,
        proposed_text="test text", strategy_version="evidence_aware",
        auto_proposable=not requires_review, requires_review=requires_review,
        uncertainty_indicators=indicators or ["UNCALIBRATED"],
        is_human_verified=False, calibration_status="UNCALIBRATED",
        created_at=now, updated_at=now,
    )


def test_is_eligible_requires_review():
    svc = RecoveryService(trocr_provider=MagicMock(), max_trocr_variants=2)
    region = make_region(confidence=0.9)
    proposal = make_proposal(requires_review=True)
    assert svc.is_eligible(region, proposal, existing_recovery_count=0) is True


def test_is_eligible_low_confidence():
    svc = RecoveryService(trocr_provider=MagicMock(), max_trocr_variants=2)
    region = make_region(confidence=0.2)
    assert svc.is_eligible(region, None, existing_recovery_count=0) is True


def test_is_eligible_budget_exhausted():
    svc = RecoveryService(trocr_provider=MagicMock(), max_trocr_variants=2)
    region = make_region(confidence=0.2)
    assert svc.is_eligible(region, None, existing_recovery_count=2) is False


def test_is_eligible_no_provider():
    svc = RecoveryService(trocr_provider=None, max_trocr_variants=2)
    region = make_region(confidence=0.2)
    assert svc.is_eligible(region, None, existing_recovery_count=0) is False


def test_is_eligible_critical_indicator():
    svc = RecoveryService(trocr_provider=MagicMock(), max_trocr_variants=2)
    region = make_region(confidence=0.9)  # High confidence
    proposal = make_proposal(requires_review=False, indicators=["CRITICAL_NUMERIC", "UNCALIBRATED"])
    assert svc.is_eligible(region, proposal, existing_recovery_count=0) is True


@pytest.mark.asyncio
async def test_attempt_recovery_no_provider_records_unavailable():
    svc = RecoveryService(trocr_provider=None, max_trocr_variants=2)
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (100, 30), color=255).save(buf, format="PNG")
    doc_bytes = buf.getvalue()
    bbox = BoundingBox(x=10, y=10, w=20, h=5)
    region = make_region()

    attempts = await svc.attempt_recovery(
        document_bytes=doc_bytes, mime_type="image/png",
        region=region, bbox=bbox, page_index=0,
        document_id="doc-1", fusion_run_id="frun-1",
        existing_hashes=set(),
    )
    assert len(attempts) >= 1
    assert all(a.outcome == RecoveryOutcome.PROVIDER_UNAVAILABLE for a in attempts)


def test_assess_outcome_neutral_same_text():
    svc = RecoveryService(trocr_provider=None)
    outcome = svc._assess_outcome("hello world", 0.9, [{"text": "hello world"}], 0.85)
    assert outcome == RecoveryOutcome.NEUTRAL


def test_assess_outcome_regressed_truncation():
    svc = RecoveryService(trocr_provider=None)
    existing = [{"text": "The north wall measures 4.8 metres in total"}]
    outcome = svc._assess_outcome("The", 0.9, existing, 0.85)
    assert outcome == RecoveryOutcome.REGRESSED


def test_assess_outcome_confidence_cannot_promote_novel_text():
    svc = RecoveryService(trocr_provider=None)
    existing = [{"text": "hello earth"}]
    outcome = svc._assess_outcome("hello world", 0.95, existing, 0.5)
    assert outcome == RecoveryOutcome.NEUTRAL


def test_assess_outcome_improved_when_recovery_corroborates_dissenting_candidate():
    svc = RecoveryService(trocr_provider=None)
    existing = [{"text": "4.8 metres"}, {"text": "4.3 metres"}]
    outcome = svc._assess_outcome("4.8 metres", 0.95, existing, 0.5)
    assert outcome == RecoveryOutcome.IMPROVED


def test_assess_outcome_no_existing_neutral():
    svc = RecoveryService(trocr_provider=None)
    outcome = svc._assess_outcome("hello world", 0.9, [], 0.8)
    assert outcome == RecoveryOutcome.NEUTRAL


def test_recovery_attempt_id_format():
    svc = RecoveryService(trocr_provider=None)
    attempt = svc._make_unavailable("r1", 0, "doc-1", "frun-1", RecoveryVariantType.ORIGINAL)
    assert attempt.id.startswith("rec-")
    assert attempt.outcome == RecoveryOutcome.PROVIDER_UNAVAILABLE

