"""RecoveryService: Bounded targeted re-inference on image variants for difficult regions.

Budget controls (all configurable via Settings):
  FUSION_MAX_TROCR_VARIANTS: max additional TrOCR inferences per region (default: 2)
  FUSION_RECOVERY_BUDGET_SECONDS: wall-clock budget per region (default: 120s)
  FUSION_MAX_CLOUD_ESCALATIONS: cloud escalations per document (default: 0 = disabled)

Safety rules:
  - SHA-256 deduplication prevents identical variant re-inference
  - BUDGET_EXHAUSTED is recorded explicitly; no silent retry
  - Recovered candidates are NEVER auto-accepted over existing proposals
  - outcome is compared against existing proposals; only IMPROVED if
    the recovered text agrees with a previously-dissenting model
  - Recovered candidates go through candidate_selection comparison again
  - is_human_verified stays False on all automated outputs (Invariant 2)
"""

import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import (
    FusionProposal,
    RecoveryAttempt,
    RecoveryOutcome,
    RecoveryVariantType,
)
from evidence_ocr.models.region import BoundingBox, RegionEntity

logger = get_logger("evidence_ocr.fusion.recovery")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RecoveryService:
    """Bounded re-inference service for difficult OCR regions."""

    def __init__(
        self,
        trocr_provider=None,
        max_trocr_variants: int = 2,
        recovery_budget_seconds: float = 120.0,
        max_cloud_escalations: int = 0,
    ) -> None:
        self.trocr_provider = trocr_provider
        self.max_trocr_variants = max_trocr_variants
        self.recovery_budget_seconds = recovery_budget_seconds
        self.max_cloud_escalations = max_cloud_escalations

    def is_eligible(
        self,
        region: RegionEntity,
        existing_proposal: Optional[FusionProposal],
        existing_recovery_count: int = 0,
    ) -> bool:
        """Determine if a region is eligible for targeted recovery.

        Eligibility requires at least one of:
          - region has disagreement (proposal.requires_review)
          - region has low confidence (< 0.40)
          - region is critical (contains numeric/date/unit conflict)

        Ineligibility if:
          - Budget already exhausted (existing_recovery_count >= max)
          - No TrOCR provider available
        """
        if self.trocr_provider is None:
            return False
        if existing_recovery_count >= self.max_trocr_variants:
            return False

        if existing_proposal:
            if existing_proposal.requires_review:
                return True
            if any(
                ind in existing_proposal.uncertainty_indicators
                for ind in ("CRITICAL_NUMERIC", "CRITICAL_DATE", "CRITICAL_UNIT")
            ):
                return True

        if region.confidence is not None and region.confidence < 0.40:
            return True

        return False

    async def attempt_recovery(
        self,
        document_bytes: bytes,
        mime_type: str,
        region: RegionEntity,
        bbox: BoundingBox,
        page_index: int,
        document_id: str,
        fusion_run_id: Optional[str],
        existing_hashes: set,
        existing_candidates: Optional[list] = None,
    ) -> List[RecoveryAttempt]:
        """Run recovery variants for a region within budget.

        Args:
            document_bytes: Original document bytes from GridFS (never modified)
            mime_type: Document MIME type
            region: The OCR region entity
            bbox: Normalized bounding box for this region
            page_index: 0-indexed page number
            document_id: Document ID for record linking
            fusion_run_id: Parent fusion run ID
            existing_hashes: Set of SHA-256 hashes already attempted (modified in place)
            existing_candidates: Existing recognized text candidates for outcome comparison

        Returns:
            List of RecoveryAttempt records (persisted by caller)
        """
        now_start = time.monotonic()
        attempts: List[RecoveryAttempt] = []
        attempts_run = 0

        if self.trocr_provider is None:
            logger.warning("TrOCR provider not available; recording PROVIDER_UNAVAILABLE")
            attempts.append(self._make_unavailable(
                region.id, page_index, document_id, fusion_run_id,
                RecoveryVariantType.ORIGINAL,
            ))
            return attempts

        from evidence_ocr.fusion.image_enhancer import generate_variants

        original_confidence = region.confidence

        # Generate candidate variants (respects budget and dedup)
        variants_budget = self.max_trocr_variants - attempts_run
        if variants_budget <= 0:
            return attempts

        try:
            variants = generate_variants(
                document_bytes=document_bytes,
                mime_type=mime_type,
                bbox=bbox,
                page_index=page_index,
                existing_hashes=existing_hashes,
                budget_remaining=variants_budget,
                original_confidence=original_confidence,
            )
        except Exception as exc:
            logger.warning("Variant generation failed for region %s: %s", region.id, exc)
            return attempts

        for variant in variants:
            if attempts_run >= self.max_trocr_variants:
                logger.debug("Max variants reached for region %s", region.id)
                break

            elapsed = time.monotonic() - now_start
            if elapsed >= self.recovery_budget_seconds:
                logger.info("Recovery budget exhausted for region %s after %.1fs", region.id, elapsed)
                attempts.append(self._make_budget_exhausted(
                    region.id, page_index, document_id, fusion_run_id,
                    variant["variant_type"], variant["sha256"], variant["params"],
                ))
                break

            vtype: RecoveryVariantType = variant["variant_type"]
            vbytes: bytes = variant["bytes"]
            sha: str = variant["sha256"]
            vparams: dict = variant["params"]

            t0 = time.monotonic()
            recovered_text: Optional[str] = None
            recovered_confidence: Optional[float] = None
            outcome = RecoveryOutcome.NEUTRAL

            try:
                result = await asyncio.wait_for(
                    self._run_trocr(vbytes, mime_type),
                    timeout=min(60.0, self.recovery_budget_seconds - elapsed),
                )
                if result:
                    recovered_text = result.get("text")
                    recovered_confidence = result.get("confidence")
                    outcome = self._assess_outcome(
                        recovered_text=recovered_text,
                        recovered_confidence=recovered_confidence,
                        existing_candidates=existing_candidates or [],
                        original_confidence=original_confidence,
                    )
            except asyncio.TimeoutError:
                logger.warning("TrOCR timeout on region %s variant %s", region.id, vtype.value)
                outcome = RecoveryOutcome.TIMEOUT
            except Exception as exc:
                logger.warning("TrOCR error on region %s variant %s: %s", region.id, vtype.value, exc)
                outcome = RecoveryOutcome.PROVIDER_UNAVAILABLE

            execution_ms = (time.monotonic() - t0) * 1000.0
            attempts_run += 1

            provider_meta = getattr(self.trocr_provider, "get_metadata", lambda: None)()
            model_version = (provider_meta.model_version if provider_meta else "trocr-base-handwritten-v1.0")

            now_str = datetime.now(timezone.utc).isoformat()
            attempts.append(RecoveryAttempt(
                id=f"rec-{uuid.uuid4().hex[:8]}",
                fusion_run_id=fusion_run_id,
                document_id=document_id,
                region_id=region.id,
                page_index=page_index,
                variant_type=vtype,
                variant_hash=sha,
                transform_params=vparams,
                model_provider="trocr",
                model_version=model_version,
                recovered_text=recovered_text,
                recovered_confidence=recovered_confidence,
                execution_time_ms=round(execution_ms, 2),
                outcome=outcome,
                created_at=now_str,
            ))

            logger.info(
                "Recovery attempt region=%s variant=%s outcome=%s time=%.0fms",
                region.id, vtype.value, outcome.value, execution_ms,
            )

        return attempts

    async def _run_trocr(self, image_bytes: bytes, mime_type: str) -> Optional[dict]:
        """Invoke TrOCR on the variant image bytes. Returns {text, confidence} or None."""
        try:
            from evidence_ocr.preprocessing.cropper import _bytes_to_pil_compat
            pass
        except ImportError:
            pass

        # The TrOCR provider's recognize_page operates on full document bytes.
        # For recovery, we pass the crop bytes as a PNG "document".
        result = await self.trocr_provider.recognize_page(
            document_bytes=image_bytes,
            mime_type="image/png",
            page_index=0,
        )
        if not result:
            return None

        # Extract text and confidence from OCRResult
        ocr_result = result
        text = ""
        confidence = None

        if hasattr(ocr_result, "regions") and ocr_result.regions:
            texts = [r.text for r in ocr_result.regions if r.text]
            text = " ".join(texts)
            confs = [r.confidence for r in ocr_result.regions if r.confidence is not None]
            confidence = sum(confs) / len(confs) if confs else None
        elif hasattr(ocr_result, "full_text"):
            text = ocr_result.full_text or ""
            confidence = getattr(ocr_result, "confidence", None)

        return {"text": text, "confidence": confidence} if text else None

    def _assess_outcome(
        self,
        recovered_text: Optional[str],
        recovered_confidence: Optional[float],
        existing_candidates: list,
        original_confidence: Optional[float],
    ) -> RecoveryOutcome:
        """Compare recovered candidate against existing candidates.

        IMPROVED: recovered text agrees with a previously-dissenting model AND
                  does not introduce new conflicts
        REGRESSED: recovered text introduces new characters not in any candidate
        NEUTRAL: no clear improvement or regression
        """
        if not recovered_text or not recovered_text.strip():
            return RecoveryOutcome.NEUTRAL

        existing_texts = [str(c.get("text", "")) for c in existing_candidates if c.get("text")]

        if not existing_texts:
            return RecoveryOutcome.NEUTRAL

        # Improvement requires corroboration from existing independent evidence.
        # Confidence alone can never promote novel text.
        recovered_norm = recovered_text.lower().strip()
        normalized_existing = {text.lower().strip() for text in existing_texts}
        if recovered_norm in normalized_existing:
            return (
                RecoveryOutcome.IMPROVED
                if len(normalized_existing) > 1
                else RecoveryOutcome.NEUTRAL
            )

        # Simple heuristic: if recovered text is shorter than all existing texts
        # by >50%, it likely truncated (regressed)
        min_existing_len = min(len(t) for t in existing_texts) if existing_texts else 1
        if len(recovered_text) < min_existing_len * 0.5:
            return RecoveryOutcome.REGRESSED

        return RecoveryOutcome.NEUTRAL

    def _make_unavailable(self, region_id, page_index, document_id, fusion_run_id, vtype) -> RecoveryAttempt:
        now = datetime.now(timezone.utc).isoformat()
        return RecoveryAttempt(
            id=f"rec-{uuid.uuid4().hex[:8]}",
            fusion_run_id=fusion_run_id,
            document_id=document_id,
            region_id=region_id,
            page_index=page_index,
            variant_type=vtype,
            variant_hash="n/a",
            transform_params={},
            model_provider="trocr",
            model_version="unavailable",
            recovered_text=None,
            recovered_confidence=None,
            execution_time_ms=0.0,
            outcome=RecoveryOutcome.PROVIDER_UNAVAILABLE,
            created_at=now,
        )

    def _make_budget_exhausted(self, region_id, page_index, document_id, fusion_run_id, vtype, sha, params) -> RecoveryAttempt:
        now = datetime.now(timezone.utc).isoformat()
        return RecoveryAttempt(
            id=f"rec-{uuid.uuid4().hex[:8]}",
            fusion_run_id=fusion_run_id,
            document_id=document_id,
            region_id=region_id,
            page_index=page_index,
            variant_type=vtype,
            variant_hash=sha,
            transform_params=params,
            model_provider="trocr",
            model_version="budget_exhausted",
            recovered_text=None,
            recovered_confidence=None,
            execution_time_ms=0.0,
            outcome=RecoveryOutcome.BUDGET_EXHAUSTED,
            created_at=now,
        )
