"""Unit tests for CandidateSelectionService."""

import pytest
from evidence_ocr.fusion.candidate_selection import CandidateSelectionService
from evidence_ocr.fusion.disagreement import DisagreementDetector
from evidence_ocr.fusion.text_aligner import TextHypothesisAligner
from evidence_ocr.models.fusion import (
    DisagreementType,
    FusionProposal,
)


def make_aligned(text_a, text_b=None, text_c=None, conf_a=0.9, conf_b=0.85):
    aligner = TextHypothesisAligner()
    candidates = [aligner.build_hypothesis_candidate("trocr", "v1", text_a, conf_a)]
    if text_b is not None:
        candidates.append(aligner.build_hypothesis_candidate("paddleocr-cloud", "PP-OCRv6", text_b, conf_b))
    if text_c is not None:
        candidates.append(aligner.build_hypothesis_candidate("paddleocr-vl-cloud", "VL-1.6", text_c, 0.8))
    return aligner.align("r1", candidates)


def make_proposal(text_a, text_b=None, strategy="evidence_aware", conf_a=0.9, conf_b=0.85):
    aligned = make_aligned(text_a, text_b, conf_a=conf_a, conf_b=conf_b)
    detector = DisagreementDetector()
    from evidence_ocr.models.region import BoundingBox, RegionEntity
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    region = RegionEntity(
        id="r1", document_id="doc-1", page_index=0, line="1",
        bounding_box=BoundingBox(x=10.0, y=10.0, w=20.0, h=5.0),
        original=text_a, reason="",
        confidence=conf_a,
        created_at=now, updated_at=now,
    )
    disagreements = detector.detect(region, aligned, None, "frun-1", "doc-1")
    svc = CandidateSelectionService(strategy=strategy)
    return svc.propose(
        region_id="r1", document_id="doc-1", page_index=0,
        fusion_run_id="frun-1", aligned=aligned, disagreements=disagreements,
        alignment=None,
    )


def test_full_agreement_auto_proposable():
    proposal = make_proposal("The north wall", "The north wall")
    assert proposal.auto_proposable is True
    assert proposal.requires_review is False
    assert proposal.proposed_text is not None


def test_numeric_conflict_never_auto_proposable():
    proposal = make_proposal("measures 4.8 metres", "measures 4.3 metres")
    assert proposal.auto_proposable is False
    assert proposal.requires_review is True


def test_numeric_conflict_indicator_present():
    proposal = make_proposal("39 items", "33 items")
    assert "CRITICAL_NUMERIC" in proposal.uncertainty_indicators


def test_calibration_status_uncalibrated():
    proposal = make_proposal("hello world", "hello world")
    assert proposal.calibration_status == "UNCALIBRATED"


def test_is_human_verified_always_false():
    proposal = make_proposal("hello world", "hello world")
    assert proposal.is_human_verified is False


def test_proposal_has_candidates():
    proposal = make_proposal("hello world", "hello earth")
    assert len(proposal.candidates) >= 1
    for c in proposal.candidates:
        assert "text" in c
        assert "source" in c


def test_full_disagreement_no_auto_propose():
    proposal = make_proposal("completely wrong text here", "totally different words now")
    assert proposal.auto_proposable is False


def test_proposed_text_not_modified_from_raw():
    raw_text = "The NORTH Wall MEASURES 4.8 metres"
    proposal = make_proposal(raw_text, raw_text)
    # proposed text should be raw, not normalized
    if proposal.proposed_text:
        assert proposal.proposed_text == raw_text


def test_evidence_reference_populated():
    proposal = make_proposal("hello world", "hello world")
    assert "region_id" in proposal.source_evidence_reference
    assert proposal.source_evidence_reference["region_id"] == "r1"


def test_proposal_id_format():
    proposal = make_proposal("hello world", "hello world")
    assert proposal.id.startswith("prop-")


def test_strategy_best_individual():
    proposal = make_proposal("The bracket below", "The basket below", strategy="best_individual")
    # Best individual = TrOCR (highest rank) 
    assert proposal.proposed_text is not None
    assert proposal.strategy_version == "best_individual"


def test_strategy_rover():
    proposal = make_proposal("The bracket below", "The basket below", strategy="unweighted_rover")
    assert proposal.proposed_text is not None
    assert proposal.strategy_version == "unweighted_rover"


def test_no_candidates_returns_requires_review():
    from evidence_ocr.fusion.candidate_selection import CandidateSelectionService
    from evidence_ocr.models.fusion import AlignedHypotheses, AgreementLevel
    svc = CandidateSelectionService()
    aligned = AlignedHypotheses(region_id="r1", overall_agreement=AgreementLevel.SINGLE_MODEL_ONLY)
    proposal = svc.propose(
        region_id="r1", document_id="doc-1", page_index=0,
        fusion_run_id="frun-1", aligned=aligned, disagreements=[],
        alignment=None,
    )
    assert proposal.requires_review is True
    assert proposal.auto_proposable is False

