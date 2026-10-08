"""Unit tests for EvidenceAlignmentService (spatial-v1)."""

import pytest

from evidence_ocr.fusion.alignment import (
    EvidenceAlignmentService,
    compute_iou,
    _contains_center,
)
from evidence_ocr.models.fusion import MatchStatus
from evidence_ocr.models.region import BoundingBox, RegionEntity


def make_bbox(x, y, w, h):
    return BoundingBox(x=x, y=y, w=w, h=h)


def make_region(rid, x, y, w, h, page=0, original="test text", confidence=0.9):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return RegionEntity(
        id=rid,
        document_id="doc-1",
        page_index=page,
        line=str(page + 1),
        original=original,
        reason="",
        bounding_box=make_bbox(x, y, w, h),
        confidence=confidence,
        created_at=now,
        updated_at=now,
    )


def make_vl_block(bid, x, y, w, h, page=0, content="test text", reading_order=1):
    from evidence_ocr.models.parsing import LayoutBlock
    return LayoutBlock(
        block_id=bid,
        page_index=page,
        block_type="text",
        bounding_box=make_bbox(x, y, w, h),
        content=content,
        reading_order=reading_order,
    )


def test_iou_identical_boxes():
    a = make_bbox(10, 10, 20, 20)
    assert compute_iou(a, a) == pytest.approx(1.0)


def test_iou_no_overlap():
    a = make_bbox(0, 0, 10, 10)
    b = make_bbox(20, 20, 10, 10)
    assert compute_iou(a, b) == pytest.approx(0.0)


def test_iou_partial_overlap():
    a = make_bbox(0, 0, 20, 20)
    b = make_bbox(10, 0, 20, 20)
    expected = 200.0 / 600.0
    assert compute_iou(a, b) == pytest.approx(expected, abs=1e-4)


def test_iou_degenerate_zero_area():
    a = BoundingBox.model_construct(x=5.0, y=5.0, w=0.0, h=0.0)
    b = make_bbox(5, 5, 10, 10)
    assert compute_iou(a, b) == pytest.approx(0.0)


def test_contains_center_yes():
    container = make_bbox(0, 0, 100, 100)
    point_box = make_bbox(40, 40, 20, 20)
    assert _contains_center(container, point_box) is True


def test_contains_center_no():
    container = make_bbox(0, 0, 30, 30)
    point_box = make_bbox(40, 40, 20, 20)
    assert _contains_center(container, point_box) is False


def test_align_single_match():
    svc = EvidenceAlignmentService()
    region = make_region("r1", x=10, y=10, w=20, h=5)
    block = make_vl_block("b1", x=10, y=10, w=20, h=5)
    alignments = svc.align([region], [block], "frun-1", "doc-1")
    matched = [a for a in alignments if a.match_status == MatchStatus.MATCHED_ONE_TO_ONE]
    assert len(matched) == 1
    assert matched[0].iou_score == pytest.approx(1.0, abs=0.01)


def test_align_no_blocks_all_unmatched():
    svc = EvidenceAlignmentService()
    regions = [make_region("r1", 10, 10, 20, 5), make_region("r2", 10, 20, 20, 5)]
    alignments = svc.align(regions, [], "frun-1", "doc-1")
    assert all(a.match_status == MatchStatus.UNMATCHED_REGION for a in alignments)
    assert len(alignments) == 2


def test_align_no_regions_block_unmatched():
    svc = EvidenceAlignmentService()
    blocks = [make_vl_block("b1", 10, 10, 20, 5)]
    alignments = svc.align([], blocks, "frun-1", "doc-1")
    assert all(a.match_status == MatchStatus.UNMATCHED_BLOCK for a in alignments)


def test_align_multi_page_isolated():
    svc = EvidenceAlignmentService()
    r0 = make_region("r0", 10, 10, 20, 5, page=0)
    r1 = make_region("r1", 10, 10, 20, 5, page=1)
    b0 = make_vl_block("b0", 10, 10, 20, 5, page=0)
    b1 = make_vl_block("b1", 10, 10, 20, 5, page=1)
    alignments = svc.align([r0, r1], [b0, b1], "frun-1", "doc-1")
    one_to_one = [a for a in alignments if a.match_status == MatchStatus.MATCHED_ONE_TO_ONE]
    assert len(one_to_one) == 2


def test_align_records_have_correct_ids():
    svc = EvidenceAlignmentService()
    region = make_region("r1", 10, 10, 20, 5)
    block = make_vl_block("b1", 10, 10, 20, 5)
    alignments = svc.align([region], [block], "frun-test", "doc-test")
    for a in alignments:
        assert a.id.startswith("align-")
        assert a.fusion_run_id == "frun-test"
        assert a.document_id == "doc-test"


def test_align_weights_stored():
    svc = EvidenceAlignmentService(weights={"w1": 0.6, "w2": 0.2, "w3": 0.1, "w4": 0.1})
    region = make_region("r1", 10, 10, 20, 5)
    block = make_vl_block("b1", 10, 10, 20, 5)
    alignments = svc.align([region], [block], "frun-1", "doc-1")
    assert any(a.weights_used.get("w1") == pytest.approx(0.6) for a in alignments)


def test_greedy_assign_picks_minimum():
    svc = EvidenceAlignmentService()
    cost = [[0.1, 0.9], [0.8, 0.2]]
    rows, cols = svc._greedy_assign(cost, 2, 2)
    assignments = list(zip(rows, cols))
    assert (0, 0) in assignments
    assert (1, 1) in assignments


def test_align_empty_inputs():
    svc = EvidenceAlignmentService()
    assert svc.align([], [], "frun-1", "doc-1") == []

