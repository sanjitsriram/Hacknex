"""EvidenceAlignmentService: Spatial bipartite matching of OCR regions to VL layout blocks.

Implements:
- Normalized IoU computation on [0, 100]% bounding boxes
- Cost matrix construction with configurable weights (treated as hypotheses)
- scipy.optimize.linear_sum_assignment for one-to-one assignments
- Containment-based one-to-many association for VL paragraph blocks
- Edge case handling: missing polygons, overlapping regions, multi-page, unmatched
"""

import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import EvidenceAlignment, MatchStatus
from evidence_ocr.models.parsing import LayoutBlock
from evidence_ocr.models.region import BoundingBox, RegionEntity

logger = get_logger("evidence_ocr.fusion.alignment")

# Default cost weights - configurable, NOT tuned; treated as engineering hypotheses
DEFAULT_WEIGHTS: Dict[str, float] = {"w1": 0.5, "w2": 0.3, "w3": 0.1, "w4": 0.1}

# Threshold above which a cost assignment is treated as UNMATCHED
UNMATCHED_COST_THRESHOLD = 0.85

# Minimum IoU to consider a pair for matching (prevents clearly non-overlapping assignments)
MIN_CANDIDATE_IOU = 0.02


def compute_iou(a: BoundingBox, b: BoundingBox) -> float:
    """Compute Intersection over Union for two normalized [0, 100]% bounding boxes.

    Mathematical definition:
        IoU = Area(A ∩ B) / Area(A ∪ B)
        where Area(A ∪ B) = Area(A) + Area(B) - Area(A ∩ B)

    Returns 0.0 if boxes do not intersect or union is degenerate.
    """
    ax1, ay1 = a.x, a.y
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx1, by1 = b.x, b.y
    bx2, by2 = b.x + b.w, b.y + b.h

    # Intersection rectangle
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = ix * iy

    area_a = a.w * a.h
    area_b = b.w * b.h
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0
    return float(intersection / union)


def vertical_center(bbox: BoundingBox) -> float:
    """Compute vertical center of a normalized bounding box."""
    return bbox.y + bbox.h / 2.0


def horizontal_overlap(a: BoundingBox, b: BoundingBox) -> float:
    """Compute normalized horizontal overlap fraction between two boxes."""
    ax1, ax2 = a.x, a.x + a.w
    bx1, bx2 = b.x, b.x + b.w
    overlap_x = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    min_width = min(a.w, b.w)
    if min_width <= 0.0:
        return 0.0
    return float(overlap_x / min_width)


def _normalize_for_text_similarity(text: str) -> str:
    """Normalize text for similarity comparison only — never stored as canonical text."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein ratio [0=identical, 1=completely different].

    Uses rapidfuzz if available, falls back to simple character comparison.
    """
    try:
        from rapidfuzz.distance import Levenshtein
        max_len = max(len(s1), len(s2), 1)
        dist = Levenshtein.distance(s1, s2)
        return float(dist / max_len)
    except ImportError:
        if s1 == s2:
            return 0.0
        return 1.0


def _contains_center(container: BoundingBox, point_bbox: BoundingBox) -> bool:
    """Return True if the center of point_bbox lies within container bbox."""
    cx = point_bbox.x + point_bbox.w / 2.0
    cy = point_bbox.y + point_bbox.h / 2.0
    return (
        container.x <= cx <= container.x + container.w
        and container.y <= cy <= container.y + container.h
    )


class EvidenceAlignmentService:
    """Spatial bipartite matching of OCR regions to VL layout blocks.

    Algorithm (spatial-v1):
    1. Validate coordinates are in [0, 100]% space.
    2. Group regions and blocks by page_index.
    3. For each page: compute cost matrix C[i][j] between regions and blocks.
    4. Set C[i][j] = IMPOSSIBLE_COST where IoU < MIN_CANDIDATE_IOU (clearly non-overlapping).
    5. Call scipy.optimize.linear_sum_assignment for one-to-one optimal assignments.
    6. Assignments with cost > UNMATCHED_COST_THRESHOLD → UNMATCHED_REGION.
    7. Containment pass: for VL blocks not consumed by step 5/6, check which region
       centers lie inside them → MATCHED_CONTAINMENT links.
    8. Remaining unmatched regions → UNMATCHED_REGION records.
    9. Remaining unmatched VL blocks → UNMATCHED_BLOCK records.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def _compute_cost(
        self,
        region: RegionEntity,
        block: LayoutBlock,
        max_reading_order_distance: int = 10,
    ) -> float:
        """Compute scalar cost for pairing (region, block).

        C(i,j) = w1*(1-IoU) + w2*norm_vertical_dist + w3*reading_order_penalty + w4*text_mismatch

        All components are normalized to [0, 1].
        Returns IMPOSSIBLE_COST for clearly non-overlapping pairs.
        """
        w1 = self.weights.get("w1", 0.5)
        w2 = self.weights.get("w2", 0.3)
        w3 = self.weights.get("w3", 0.1)
        w4 = self.weights.get("w4", 0.1)

        iou = compute_iou(region.bounding_box, block.bounding_box)

        # IoU-based gating: if clearly non-overlapping, return high cost
        if iou < MIN_CANDIDATE_IOU:
            horiz = horizontal_overlap(region.bounding_box, block.bounding_box)
            if horiz < 0.1:
                return 999.0  # IMPOSSIBLE

        cost_iou = 1.0 - iou

        # Vertical center distance normalized to [0, 1] (page height = 100)
        vc_region = vertical_center(region.bounding_box)
        vc_block = vertical_center(block.bounding_box)
        cost_vertical = abs(vc_region - vc_block) / 100.0

        # Reading order penalty: if region has a reading order implied by its ID sequence
        # and block has an explicit reading_order field
        reading_order_block = block.reading_order if block.reading_order else 0
        reading_order_region = 0  # OCR regions don't have explicit reading order
        if reading_order_block > 0:
            order_diff = abs(reading_order_region - reading_order_block)
            cost_order = min(1.0, order_diff / max_reading_order_distance)
        else:
            cost_order = 0.0

        # Text mismatch: normalized Levenshtein on truncated normalized content
        region_text_norm = _normalize_for_text_similarity(region.original or "")
        block_text_norm = _normalize_for_text_similarity(block.content or "")
        # Limit comparison to first 100 chars to bound complexity
        cost_text = _levenshtein_ratio(region_text_norm[:100], block_text_norm[:100])

        return w1 * cost_iou + w2 * cost_vertical + w3 * cost_order + w4 * cost_text

    def align(
        self,
        regions: List[RegionEntity],
        vl_blocks: List[LayoutBlock],
        fusion_run_id: str,
        document_id: str,
    ) -> List[EvidenceAlignment]:
        """Run spatial alignment and return EvidenceAlignment records.

        Uses scipy.optimize.linear_sum_assignment when available;
        falls back to greedy nearest-neighbor if scipy is unavailable.
        """
        now = datetime.now(timezone.utc).isoformat()
        alignments: List[EvidenceAlignment] = []

        # Group by page
        page_indices = set(r.page_index for r in regions) | set(b.page_index for b in vl_blocks)

        for page_idx in sorted(page_indices):
            page_regions = [r for r in regions if r.page_index == page_idx]
            page_blocks = [b for b in vl_blocks if b.page_index == page_idx]

            if not page_regions and not page_blocks:
                continue

            aligned_region_ids: set = set()
            aligned_block_ids: set = set()

            if page_regions and page_blocks:
                # Build cost matrix
                n_regions = len(page_regions)
                n_blocks = len(page_blocks)
                cost_matrix = [[0.0] * n_blocks for _ in range(n_regions)]

                for i, region in enumerate(page_regions):
                    for j, block in enumerate(page_blocks):
                        cost_matrix[i][j] = self._compute_cost(region, block)

                # Run Hungarian assignment
                row_ind, col_ind = self._linear_assign(cost_matrix, n_regions, n_blocks)

                for i, j in zip(row_ind, col_ind):
                    region = page_regions[i]
                    block = page_blocks[j]
                    cost_val = cost_matrix[i][j]
                    iou_val = compute_iou(region.bounding_box, block.bounding_box)

                    if cost_val > UNMATCHED_COST_THRESHOLD or cost_val >= 999.0:
                        # Cost too high: treat as unmatched
                        continue

                    aligned_region_ids.add(region.id)
                    aligned_block_ids.add(block.block_id)
                    match_conf = max(0.0, min(1.0, 1.0 - cost_val))

                    alignments.append(EvidenceAlignment(
                        id=f"align-{uuid.uuid4().hex[:8]}",
                        fusion_run_id=fusion_run_id,
                        document_id=document_id,
                        page_index=page_idx,
                        region_id=region.id,
                        vl_block_id=block.block_id,
                        match_status=MatchStatus.MATCHED_ONE_TO_ONE,
                        iou_score=round(iou_val, 4),
                        cost_value=round(cost_val, 4),
                        match_confidence=round(match_conf, 4),
                        weights_used=self.weights.copy(),
                        reading_order_region=None,
                        reading_order_block=block.reading_order,
                        created_at=now,
                    ))

                # Containment pass: match remaining regions whose centers fall inside unmatched blocks
                for block in page_blocks:
                    if block.block_id in aligned_block_ids:
                        continue
                    contained: List[RegionEntity] = []
                    for region in page_regions:
                        if region.id in aligned_region_ids:
                            continue
                        if _contains_center(block.bounding_box, region.bounding_box):
                            contained.append(region)

                    for region in contained:
                        aligned_region_ids.add(region.id)
                        aligned_block_ids.add(block.block_id)
                        iou_val = compute_iou(region.bounding_box, block.bounding_box)
                        alignments.append(EvidenceAlignment(
                            id=f"align-{uuid.uuid4().hex[:8]}",
                            fusion_run_id=fusion_run_id,
                            document_id=document_id,
                            page_index=page_idx,
                            region_id=region.id,
                            vl_block_id=block.block_id,
                            match_status=MatchStatus.MATCHED_CONTAINMENT,
                            iou_score=round(iou_val, 4),
                            cost_value=None,
                            match_confidence=0.6,
                            weights_used=self.weights.copy(),
                            reading_order_region=None,
                            reading_order_block=block.reading_order,
                            created_at=now,
                        ))

            # Unmatched regions
            for region in page_regions:
                if region.id not in aligned_region_ids:
                    alignments.append(EvidenceAlignment(
                        id=f"align-{uuid.uuid4().hex[:8]}",
                        fusion_run_id=fusion_run_id,
                        document_id=document_id,
                        page_index=page_idx,
                        region_id=region.id,
                        vl_block_id=None,
                        match_status=MatchStatus.UNMATCHED_REGION,
                        iou_score=None,
                        cost_value=None,
                        match_confidence=0.0,
                        weights_used=self.weights.copy(),
                        reading_order_region=None,
                        reading_order_block=None,
                        created_at=now,
                    ))

            # Unmatched VL blocks
            for block in page_blocks:
                if block.block_id not in aligned_block_ids:
                    alignments.append(EvidenceAlignment(
                        id=f"align-{uuid.uuid4().hex[:8]}",
                        fusion_run_id=fusion_run_id,
                        document_id=document_id,
                        page_index=page_idx,
                        region_id=None,
                        vl_block_id=block.block_id,
                        match_status=MatchStatus.UNMATCHED_BLOCK,
                        iou_score=None,
                        cost_value=None,
                        match_confidence=0.0,
                        weights_used=self.weights.copy(),
                        reading_order_region=None,
                        reading_order_block=block.reading_order,
                        created_at=now,
                    ))

        logger.info(
            "Alignment complete: %d alignments from %d regions and %d VL blocks",
            len(alignments), len(regions), len(vl_blocks),
        )
        return alignments

    def _linear_assign(
        self, cost_matrix: List[List[float]], n_rows: int, n_cols: int
    ) -> Tuple[List[int], List[int]]:
        """Wrapper for scipy.optimize.linear_sum_assignment with graceful fallback."""
        try:
            import numpy as np
            from scipy.optimize import linear_sum_assignment
            cm_np = np.array(cost_matrix)
            row_ind, col_ind = linear_sum_assignment(cm_np)
            return list(row_ind), list(col_ind)
        except ImportError:
            logger.warning("scipy/numpy not available; using greedy nearest-neighbor fallback")
            return self._greedy_assign(cost_matrix, n_rows, n_cols)

    @staticmethod
    def _greedy_assign(
        cost_matrix: List[List[float]], n_rows: int, n_cols: int
    ) -> Tuple[List[int], List[int]]:
        """Greedy fallback: iteratively pick minimum-cost unassigned pair."""
        assigned_rows: set = set()
        assigned_cols: set = set()
        pairs: List[Tuple[float, int, int]] = []

        for i in range(n_rows):
            for j in range(n_cols):
                pairs.append((cost_matrix[i][j], i, j))
        pairs.sort(key=lambda x: x[0])

        row_ind, col_ind = [], []
        for cost, i, j in pairs:
            if i not in assigned_rows and j not in assigned_cols:
                assigned_rows.add(i)
                assigned_cols.add(j)
                row_ind.append(i)
                col_ind.append(j)

        return row_ind, col_ind
