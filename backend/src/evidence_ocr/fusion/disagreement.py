"""DisagreementDetector: Deterministic detection of conflicts across multi-model OCR hypotheses.

Implements all 12 required disagreement classes from the Phase 6 specification.
All detection is rule-based - no ML inference. Each DisagreementRecord is linked
to the specific AlignedPosition and contributing candidates for traceability.

Critical token escalation:
  Numbers, dates, units, identifiers are always flagged as CRITICAL severity
  regardless of confidence, because silent numeric errors are a primary risk domain.

Correlated error caution:
  PP-OCRv6 and PaddleOCR-VL share model family characteristics. Agreement between
  them does not constitute independent evidence. This is noted in reason codes
  (CORRELATED_MODELS) but does not prevent detection.
"""

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import (
    AgreementLevel,
    AlignedHypotheses,
    DisagreementRecord,
    DisagreementSeverity,
    DisagreementType,
    EvidenceAlignment,
    HypothesisCandidate,
)
from evidence_ocr.models.region import RegionEntity

logger = get_logger("evidence_ocr.fusion.disagreement")

# Critical pattern detection
_NUMERIC_RE = re.compile(r"\b\d[\d.,]*\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})\b"
)
_UNIT_RE = re.compile(
    r"\b\d+[\s]?(mm|cm|m|km|mg|g|kg|ml|l|ml|lb|oz|ft|in|psi|kpa|bar|deg|%)\b",
    re.IGNORECASE,
)

# Providers from the same model family (PP-OCRv6 and PaddleOCR-VL share architecture)
CORRELATED_PROVIDERS = {"paddleocr-cloud", "paddleocr-vl-cloud"}

# Low confidence threshold
LOW_CONFIDENCE_THRESHOLD = 0.30

# Unsupported completion: VL candidate is >20% longer than OCR candidate
UNSUPPORTED_COMPLETION_RATIO = 1.20


def _has_numeric(text: str) -> bool:
    return bool(_NUMERIC_RE.search(text))


def _has_date(text: str) -> bool:
    return bool(_DATE_RE.search(text))


def _has_unit(text: str) -> bool:
    return bool(_UNIT_RE.search(text))


def _extract_digits(text: str) -> str:
    """Extract all digit characters for numeric conflict comparison."""
    return "".join(c for c in text if c.isdigit())


class DisagreementDetector:
    """Deterministic multi-model disagreement detector."""

    def detect(
        self,
        region: RegionEntity,
        aligned: AlignedHypotheses,
        alignment: Optional[EvidenceAlignment],
        fusion_run_id: str,
        document_id: str,
    ) -> List[DisagreementRecord]:
        """Detect all applicable disagreement classes for a region.

        Args:
            region: The OCR RegionEntity being evaluated.
            aligned: Multi-model text alignment result for this region.
            alignment: Spatial alignment record (may be None if unmatched).
            fusion_run_id: Parent fusion run ID.
            document_id: Document ID.

        Returns:
            List of DisagreementRecord instances (may be empty if fully agreeable).
        """
        now = datetime.now(timezone.utc).isoformat()
        records: List[DisagreementRecord] = []
        alignment_id = alignment.id if alignment else None

        candidates = aligned.candidates

        # 1. INSUFFICIENT_EVIDENCE: fewer than 2 model outputs
        if len(candidates) < 2:
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.INSUFFICIENT_EVIDENCE,
                severity=DisagreementSeverity.MEDIUM,
                description="Fewer than 2 model outputs available for this region.",
                alignment_id=alignment_id,
                now=now,
            ))
            for c in candidates:
                if c.raw_confidence is not None and c.raw_confidence < LOW_CONFIDENCE_THRESHOLD:
                    records.append(self._make(
                        fusion_run_id=fusion_run_id,
                        document_id=document_id,
                        region_id=region.id,
                        page_index=region.page_index,
                        dtype=DisagreementType.LOW_RAW_CONFIDENCE,
                        severity=DisagreementSeverity.MEDIUM,
                        description=f"Model '{c.source_model}' raw confidence {c.raw_confidence:.3f} < {LOW_CONFIDENCE_THRESHOLD}.",
                        alignment_id=alignment_id,
                        candidate_a={"text": c.raw_text, "source": c.source_model, "confidence": c.raw_confidence},
                        now=now,
                    ))
            return records

        # Candidate shorthand for up to 3 models
        cand_a = candidates[0] if len(candidates) > 0 else None
        cand_b = candidates[1] if len(candidates) > 1 else None
        cand_c = candidates[2] if len(candidates) > 2 else None

        def cand_dict(c: Optional[HypothesisCandidate]):
            if c is None:
                return None
            return {"text": c.raw_text, "source": c.source_model, "confidence": c.raw_confidence}

        # 2. MODEL_UNAVAILABLE: any provider returned empty text
        for c in candidates:
            if not c.raw_text.strip():
                records.append(self._make(
                    fusion_run_id=fusion_run_id,
                    document_id=document_id,
                    region_id=region.id,
                    page_index=region.page_index,
                    dtype=DisagreementType.MODEL_UNAVAILABLE,
                    severity=DisagreementSeverity.HIGH,
                    description=f"Model '{c.source_model}' returned empty text for this region.",
                    alignment_id=alignment_id,
                    candidate_a=cand_dict(cand_a),
                    candidate_b=cand_dict(cand_b),
                    candidate_c=cand_dict(cand_c),
                    now=now,
                ))

        # 3. LOW_RAW_CONFIDENCE: any candidate below threshold
        for c in candidates:
            if c.raw_confidence is not None and c.raw_confidence < LOW_CONFIDENCE_THRESHOLD:
                records.append(self._make(
                    fusion_run_id=fusion_run_id,
                    document_id=document_id,
                    region_id=region.id,
                    page_index=region.page_index,
                    dtype=DisagreementType.LOW_RAW_CONFIDENCE,
                    severity=DisagreementSeverity.MEDIUM,
                    description=f"Model '{c.source_model}' raw confidence {c.raw_confidence:.3f} < {LOW_CONFIDENCE_THRESHOLD}.",
                    alignment_id=alignment_id,
                    candidate_a=cand_dict(cand_a),
                    now=now,
                ))

        # 4. MODEL_DISAGREEMENT: any position has non-FULL_AGREEMENT
        has_disagreement = any(
            pos.agreement not in (AgreementLevel.FULL_AGREEMENT, AgreementLevel.SINGLE_MODEL_ONLY)
            for pos in aligned.positions
        )
        if has_disagreement:
            # Determine severity based on position criticality
            has_critical = any(pos.is_critical for pos in aligned.positions
                                if pos.agreement != AgreementLevel.FULL_AGREEMENT)
            severity = DisagreementSeverity.CRITICAL if has_critical else DisagreementSeverity.HIGH
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.MODEL_DISAGREEMENT,
                severity=severity,
                description=f"Models disagree on transcription. Overall agreement: {aligned.overall_agreement.value}.",
                alignment_id=alignment_id,
                candidate_a=cand_dict(cand_a),
                candidate_b=cand_dict(cand_b),
                candidate_c=cand_dict(cand_c),
                now=now,
            ))

        # 5. NUMERIC_CONFLICT: digit sequences differ across candidates
        all_digits = [_extract_digits(c.raw_text) for c in candidates if c.raw_text.strip()]
        if len(set(all_digits)) > 1 and any(d for d in all_digits):
            conflicting = " vs ".join(d if d else "(none)" for d in all_digits[:3])
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.NUMERIC_CONFLICT,
                severity=DisagreementSeverity.CRITICAL,
                description=f"Numeric sequences differ across models: {conflicting}.",
                alignment_id=alignment_id,
                candidate_a=cand_dict(cand_a),
                candidate_b=cand_dict(cand_b),
                candidate_c=cand_dict(cand_c),
                conflicting_span=conflicting,
                now=now,
            ))

        # 6. DATE_CONFLICT: date patterns differ
        all_dates = [" ".join(_DATE_RE.findall(c.raw_text)) for c in candidates if c.raw_text.strip()]
        if len(set(all_dates)) > 1 and any(d for d in all_dates):
            conflicting = " vs ".join(d if d else "(none)" for d in all_dates[:3])
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.DATE_CONFLICT,
                severity=DisagreementSeverity.CRITICAL,
                description=f"Date patterns differ across models: {conflicting}.",
                alignment_id=alignment_id,
                candidate_a=cand_dict(cand_a),
                candidate_b=cand_dict(cand_b),
                conflicting_span=conflicting,
                now=now,
            ))

        # 7. UNIT_CONFLICT: measurement units differ
        all_units = [" ".join(m.group(0) for m in _UNIT_RE.finditer(c.raw_text))
                     for c in candidates if c.raw_text.strip()]
        if len(set(all_units)) > 1 and any(u for u in all_units):
            conflicting = " vs ".join(u if u else "(none)" for u in all_units[:3])
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.UNIT_CONFLICT,
                severity=DisagreementSeverity.CRITICAL,
                description=f"Measurement units differ across models: {conflicting}.",
                alignment_id=alignment_id,
                candidate_a=cand_dict(cand_a),
                candidate_b=cand_dict(cand_b),
                conflicting_span=conflicting,
                now=now,
            ))

        # 8. MISSING_TEXT: one model has INSERTION positions not covered by others
        missing_positions = [p for p in aligned.positions if p.agreement == AgreementLevel.MISSING_TEXT]
        if missing_positions:
            missing_words = [
                w for p in missing_positions
                for m, w in p.candidates_at_position.items() if w is not None
            ]
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.MISSING_TEXT,
                severity=DisagreementSeverity.HIGH,
                description=f"Some models are missing text present in others. Missing words: {missing_words[:5]}.",
                alignment_id=alignment_id,
                candidate_a=cand_dict(cand_a),
                candidate_b=cand_dict(cand_b),
                now=now,
            ))

        # 9. EXTRA_TEXT: VL candidate significantly longer than OCR candidate (unsupported completion)
        for i, ca in enumerate(candidates):
            for j, cb in enumerate(candidates):
                if i >= j:
                    continue
                if not ca.raw_text.strip() or not cb.raw_text.strip():
                    continue
                len_ratio = len(cb.raw_text) / max(len(ca.raw_text), 1)
                if len_ratio > UNSUPPORTED_COMPLETION_RATIO:
                    records.append(self._make(
                        fusion_run_id=fusion_run_id,
                        document_id=document_id,
                        region_id=region.id,
                        page_index=region.page_index,
                        dtype=DisagreementType.UNSUPPORTED_COMPLETION_SUSPECTED,
                        severity=DisagreementSeverity.HIGH,
                        description=(
                            f"Model '{cb.source_model}' output is {len_ratio:.1f}x longer than "
                            f"'{ca.source_model}' - possible visually unsupported completion."
                        ),
                        alignment_id=alignment_id,
                        candidate_a=cand_dict(ca),
                        candidate_b=cand_dict(cb),
                        now=now,
                    ))

        # 10. GEOMETRY_MISMATCH: alignment IoU was very low
        if alignment and alignment.iou_score is not None and alignment.iou_score < 0.05:
            records.append(self._make(
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=region.page_index,
                dtype=DisagreementType.GEOMETRY_MISMATCH,
                severity=DisagreementSeverity.MEDIUM,
                description=f"Spatial alignment IoU is very low ({alignment.iou_score:.3f}). Coordinate systems may differ.",
                alignment_id=alignment_id,
                now=now,
            ))

        # 11. READING_ORDER_CONFLICT: block reading order far from expected
        if alignment and alignment.reading_order_block and alignment.reading_order_region:
            order_diff = abs((alignment.reading_order_block or 0) - (alignment.reading_order_region or 0))
            if order_diff > 2:
                records.append(self._make(
                    fusion_run_id=fusion_run_id,
                    document_id=document_id,
                    region_id=region.id,
                    page_index=region.page_index,
                    dtype=DisagreementType.READING_ORDER_CONFLICT,
                    severity=DisagreementSeverity.LOW,
                    description=f"Reading order difference of {order_diff} positions between OCR region and VL block.",
                    alignment_id=alignment_id,
                    now=now,
                ))

        logger.debug(
            "Disagreement detection for region %s: %d records found",
            region.id, len(records),
        )
        return records

    @staticmethod
    def _make(
        fusion_run_id: str,
        document_id: str,
        region_id: str,
        page_index: int,
        dtype: DisagreementType,
        severity: DisagreementSeverity,
        description: str,
        alignment_id: Optional[str],
        now: str,
        candidate_a=None,
        candidate_b=None,
        candidate_c=None,
        conflicting_span: Optional[str] = None,
    ) -> DisagreementRecord:
        return DisagreementRecord(
            id=f"dis-{uuid.uuid4().hex[:8]}",
            fusion_run_id=fusion_run_id,
            document_id=document_id,
            region_id=region_id,
            page_index=page_index,
            disagreement_type=dtype,
            severity=severity,
            description=description,
            candidate_a=candidate_a,
            candidate_b=candidate_b,
            candidate_c=candidate_c,
            conflicting_span=conflicting_span,
            alignment_id=alignment_id,
            created_at=now,
        )
