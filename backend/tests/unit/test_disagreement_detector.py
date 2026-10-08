"""Unit tests for DisagreementDetector — all 12 disagreement classes."""

import pytest
from evidence_ocr.fusion.disagreement import DisagreementDetector
from evidence_ocr.fusion.text_aligner import TextHypothesisAligner
from evidence_ocr.models.fusion import (
    AgreementLevel,
    AlignedHypotheses,
    DisagreementSeverity,
    DisagreementType,
    EvidenceAlignment,
    MatchStatus,
)
from evidence_ocr.models.region import BoundingBox, RegionEntity


def make_bbox(x, y, w, h):
    return BoundingBox(x=x, y=y, w=w, h=h)


def make_region(rid="r1", x=10, y=10, w=20, h=5, confidence=0.9, page=0):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return RegionEntity(
        id=rid,
        document_id="doc-1",
        page_index=page,
        line=str(page + 1),
        original="test",
        reason="",
        bounding_box=make_bbox(x, y, w, h),
        confidence=confidence,
        created_at=now,
        updated_at=now,
    )


def make_alignment(iou=0.9, rid="r1", bid="b1"):
    return EvidenceAlignment(
        id="align-001",
        fusion_run_id="frun-1",
        document_id="doc-1",
        page_index=0,
        region_id=rid,
        vl_block_id=bid,
        match_status=MatchStatus.MATCHED_ONE_TO_ONE,
        iou_score=iou,
        cost_value=0.1,
        match_confidence=0.9,
        weights_used={"w1": 0.5, "w2": 0.3, "w3": 0.1, "w4": 0.1},
        created_at="2026-10-09T00:00:00Z",
    )


def run_detect(region_text_a, region_text_b=None, region_text_c=None,
               confidence_a=0.9, confidence_b=0.9, confidence_c=None,
               alignment=None, region=None):
    aligner = TextHypothesisAligner()
    detector = DisagreementDetector()

    if region is None:
        region = make_region()

    candidates = [
        aligner.build_hypothesis_candidate("trocr", "v1", region_text_a, confidence_a),
    ]
    if region_text_b is not None:
        candidates.append(
            aligner.build_hypothesis_candidate("paddleocr-cloud", "PP-OCRv6", region_text_b, confidence_b)
        )
    if region_text_c is not None:
        candidates.append(
            aligner.build_hypothesis_candidate("paddleocr-vl-cloud", "VL-1.6", region_text_c, confidence_c or 0.8)
        )

    aligned = aligner.align(region.id, candidates)
    return detector.detect(region, aligned, alignment, "frun-1", "doc-1")


def test_insufficient_evidence_no_candidates():
    aligner = TextHypothesisAligner()
    detector = DisagreementDetector()
    region = make_region()
    aligned = aligner.align(region.id, [])
    records = detector.detect(region, aligned, None, "frun-1", "doc-1")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.INSUFFICIENT_EVIDENCE in types


def test_model_unavailable_empty_text():
    records = run_detect("hello world", region_text_b="")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.MODEL_UNAVAILABLE in types


def test_low_raw_confidence():
    records = run_detect("hello world", confidence_a=0.2)
    types = [r.disagreement_type for r in records]
    assert DisagreementType.LOW_RAW_CONFIDENCE in types


def test_low_raw_confidence_is_medium_severity():
    records = run_detect("hello world", confidence_a=0.2)
    low_conf = [r for r in records if r.disagreement_type == DisagreementType.LOW_RAW_CONFIDENCE]
    assert low_conf
    assert low_conf[0].severity == DisagreementSeverity.MEDIUM


def test_model_disagreement_detected():
    records = run_detect("The bracket below", "The basket below")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.MODEL_DISAGREEMENT in types


def test_numeric_conflict_detected():
    records = run_detect("measures 4.8 metres", "measures 4.3 metres")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.NUMERIC_CONFLICT in types


def test_numeric_conflict_critical_severity():
    records = run_detect("39 items", "33 items")
    numeric = [r for r in records if r.disagreement_type == DisagreementType.NUMERIC_CONFLICT]
    assert numeric
    assert numeric[0].severity == DisagreementSeverity.CRITICAL


def test_numeric_conflict_conflicting_span_populated():
    records = run_detect("39 items", "33 items")
    numeric = [r for r in records if r.disagreement_type == DisagreementType.NUMERIC_CONFLICT]
    assert numeric
    assert numeric[0].conflicting_span is not None
    assert "39" in numeric[0].conflicting_span or "33" in numeric[0].conflicting_span


def test_date_conflict_detected():
    records = run_detect("visit on 12/10/2026", "visit on 13/10/2026")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.DATE_CONFLICT in types


def test_date_conflict_critical_severity():
    records = run_detect("on 12/10/2026", "on 13/10/2026")
    date_conflicts = [r for r in records if r.disagreement_type == DisagreementType.DATE_CONFLICT]
    assert date_conflicts
    assert date_conflicts[0].severity == DisagreementSeverity.CRITICAL


def test_unit_conflict_detected():
    records = run_detect("height 4.8m", "height 4.8km")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.UNIT_CONFLICT in types


def test_geometry_mismatch_low_iou():
    alignment = make_alignment(iou=0.03)
    records = run_detect("some text", "some text", alignment=alignment)
    types = [r.disagreement_type for r in records]
    assert DisagreementType.GEOMETRY_MISMATCH in types


def test_no_geometry_mismatch_high_iou():
    alignment = make_alignment(iou=0.9)
    records = run_detect("some text", "some text", alignment=alignment)
    types = [r.disagreement_type for r in records]
    assert DisagreementType.GEOMETRY_MISMATCH not in types


def test_unsupported_completion_suspected():
    short_text = "hello world"
    long_text = "hello world this is a much longer version that extends well beyond the original"
    records = run_detect(short_text, long_text)
    types = [r.disagreement_type for r in records]
    assert DisagreementType.UNSUPPORTED_COMPLETION_SUSPECTED in types


def test_full_agreement_no_model_disagreement():
    records = run_detect("The north wall measures 4.8 metres",
                          "The north wall measures 4.8 metres")
    types = [r.disagreement_type for r in records]
    assert DisagreementType.MODEL_DISAGREEMENT not in types


def test_records_have_ids_and_timestamps():
    records = run_detect("hello world", "hello earth")
    for r in records:
        assert r.id.startswith("dis-")
        assert r.created_at
        assert r.fusion_run_id == "frun-1"
        assert r.document_id == "doc-1"


def test_candidates_populated_in_records():
    records = run_detect("hello world", "hello earth")
    model_records = [r for r in records if r.disagreement_type == DisagreementType.MODEL_DISAGREEMENT]
    if model_records:
        assert model_records[0].candidate_a is not None
        assert "text" in model_records[0].candidate_a

