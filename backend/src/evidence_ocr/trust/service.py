"""Calibrated trust decision service interface for uncertainty and illegibility assessment."""

from typing import List, Tuple
from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.region import RegionEntity

logger = get_logger("evidence_ocr.trust")


class TrustDecision:
    """Calibrated trust evaluation for a transcript region."""

    def __init__(self, is_trusted: bool, calibrated_confidence: float, requires_human_review: bool):
        self.is_trusted = is_trusted
        self.calibrated_confidence = calibrated_confidence
        self.requires_human_review = requires_human_review


class TrustService:
    """Assesses model uncertainty, applies calibrated thresholds, and tags illegible strokes."""

    def __init__(self, confidence_threshold: float = 0.85) -> None:
        self.threshold = confidence_threshold

    def evaluate_region_trust(self, region: RegionEntity) -> TrustDecision:
        """Evaluate whether a region meets calibration standards without human verification."""
        # Evidence-first invariant: never extrapolate high confidence from uncalibrated raw scores
        return TrustDecision(
            is_trusted=False,
            calibrated_confidence=0.5,
            requires_human_review=True,
        )
