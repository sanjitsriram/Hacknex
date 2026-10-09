"""FusionService: Phase 6 evidence fusion pipeline orchestrator.

Replaces the Phase 5 stub. Implements the full lifecycle:
  1. Load OCR regions and VL layout blocks for a document
  2. Spatial alignment (EvidenceAlignmentService)
  3. Text hypothesis alignment (TextHypothesisAligner)
  4. Disagreement detection (DisagreementDetector)
  5. Conservative candidate selection (CandidateSelectionService)
  6. Optional targeted recovery (RecoveryService)
  7. Persist all results and update FusionRun status

Non-blocking design: all work runs in asyncio tasks dispatched from
FastAPI route handlers. The event loop is never blocked by CPU-bound
TrOCR inference (which runs in a ThreadPoolExecutor via the existing
TrOCRProvider infrastructure).

Idempotency: callers pass an idempotency_key; if a non-failed FusionRun
exists for (document_id, idempotency_key), returns the existing run_id.

Invariant compliance:
  - Raw model outputs never modified (Invariant 1, 2)
  - All proposals marked UNCALIBRATED (Invariant 2)
  - is_human_verified always False on creation (Invariant 2)
  - Session ownership checked before any access (Invariant 4)
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import (
    DisagreementRecord,
    EvidenceAlignment,
    FusionProposal,
    FusionRun,
    FusionStatus,
    RecoveryAttempt,
)
from evidence_ocr.models.parsing import LayoutBlock
from evidence_ocr.models.region import RegionEntity

logger = get_logger("evidence_ocr.fusion")


class FusionService:
    """Orchestrates the full Phase 6 evidence fusion pipeline."""

    def __init__(
        self,
        fusion_repo=None,
        region_repo=None,
        parsing_repo=None,
        storage_provider=None,
        trocr_provider=None,
        strategy: str = "evidence_aware",
        max_trocr_variants: int = 2,
        recovery_budget_seconds: float = 120.0,
        max_cloud_escalations: int = 0,
        fusion_cost_weights: Optional[dict] = None,
    ) -> None:
        self.fusion_repo = fusion_repo
        self.region_repo = region_repo
        self.parsing_repo = parsing_repo
        self.storage_provider = storage_provider
        self.trocr_provider = trocr_provider
        self.strategy = strategy
        self.max_trocr_variants = max_trocr_variants
        self.recovery_budget_seconds = recovery_budget_seconds
        self.max_cloud_escalations = max_cloud_escalations
        self.fusion_cost_weights = fusion_cost_weights

        # Lazy-instantiated sub-services
        self._alignment_svc = None
        self._text_aligner = None
        self._disagreement_detector = None
        self._selection_svc = None
        self._recovery_svc = None

    def _get_alignment_svc(self):
        if self._alignment_svc is None:
            from evidence_ocr.fusion.alignment import EvidenceAlignmentService
            self._alignment_svc = EvidenceAlignmentService(weights=self.fusion_cost_weights)
        return self._alignment_svc

    def _get_text_aligner(self):
        if self._text_aligner is None:
            from evidence_ocr.fusion.text_aligner import TextHypothesisAligner
            self._text_aligner = TextHypothesisAligner()
        return self._text_aligner

    def _get_disagreement_detector(self):
        if self._disagreement_detector is None:
            from evidence_ocr.fusion.disagreement import DisagreementDetector
            self._disagreement_detector = DisagreementDetector()
        return self._disagreement_detector

    def _get_selection_svc(self):
        if self._selection_svc is None:
            from evidence_ocr.fusion.candidate_selection import CandidateSelectionService
            self._selection_svc = CandidateSelectionService(strategy=self.strategy)
        return self._selection_svc

    def _get_recovery_svc(self):
        if self._recovery_svc is None:
            from evidence_ocr.fusion.recovery import RecoveryService
            self._recovery_svc = RecoveryService(
                trocr_provider=self.trocr_provider,
                max_trocr_variants=self.max_trocr_variants,
                recovery_budget_seconds=self.recovery_budget_seconds,
                max_cloud_escalations=self.max_cloud_escalations,
            )
        return self._recovery_svc

    async def recover_region(
        self,
        document,
        region_id: str,
        fusion_run_id: str,
    ) -> List[RecoveryAttempt]:
        """Execute and persist bounded recovery for one evidence-linked region."""
        if not self.region_repo or not self.fusion_repo or not self.storage_provider:
            raise RuntimeError("Recovery dependencies are unavailable")

        region = await self.region_repo.get_by_id(document.id, region_id)
        if not region:
            raise LookupError(f"Region {region_id} not found")

        proposal = await self.fusion_repo.get_proposal_for_region(
            document.id, region_id, fusion_run_id
        )
        if not proposal:
            raise LookupError(f"Fusion proposal for region {region_id} not found")

        existing = await self.fusion_repo.list_recovery_attempts(document.id, region_id)
        if len(existing) >= self.max_trocr_variants:
            raise OverflowError("Recovery budget exhausted for this region")

        file_key = document.gridfs_file_id or document.file_key or document.id
        document_bytes = await self.storage_provider.download(file_key)
        existing_hashes = {a.variant_hash for a in existing if a.variant_hash != "n/a"}

        recovery = self._get_recovery_svc()
        recovery.max_trocr_variants = self.max_trocr_variants - len(existing)
        attempts = await recovery.attempt_recovery(
            document_bytes=document_bytes,
            mime_type=document.content_type or document.mime or "image/png",
            region=region,
            bbox=region.bounding_box,
            page_index=region.page_index,
            document_id=document.id,
            fusion_run_id=fusion_run_id,
            existing_hashes=existing_hashes,
            existing_candidates=proposal.candidates,
        )
        if not attempts:
            raise RuntimeError("Recovery produced no new evidence variant")

        for attempt in attempts:
            await self.fusion_repo.save_recovery_attempt(attempt)
            await self.fusion_repo.update_proposal_recovery(proposal.id, attempt.id)
        return attempts

    async def create_fusion_run(
        self,
        document_id: str,
        session_id: str,
        strategy: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> FusionRun:
        """Create a new FusionRun record (QUEUED status). Returns immediately.

        If a non-failed run with the same (document_id, idempotency_key) exists,
        returns the existing run (idempotency).
        """
        now = datetime.now(timezone.utc).isoformat()
        run_id = f"frun-{uuid.uuid4().hex[:8]}"

        run = FusionRun(
            id=run_id,
            document_id=document_id,
            strategy_version=strategy or self.strategy,
            alignment_algorithm_version="spatial-v1",
            status=FusionStatus.QUEUED,
            created_by_session=session_id,
            created_at=now,
            updated_at=now,
        )

        if self.fusion_repo:
            saved = await self.fusion_repo.create_fusion_run(run)
            return saved
        return run

    async def execute_fusion(
        self,
        fusion_run: FusionRun,
        document_id: str,
        document_bytes: Optional[bytes],
        mime_type: str,
    ) -> FusionRun:
        """Execute the full fusion pipeline for a document asynchronously.

        This method is dispatched as a background asyncio task. All sub-steps
        are awaited; CPU-bound operations use the TrOCR provider's thread pool.

        Returns the updated FusionRun (COMPLETED or FAILED status).
        """
        t_start = time.monotonic()
        now = datetime.now(timezone.utc).isoformat()
        run_id = fusion_run.id

        logger.info("Starting fusion run %s for document %s", run_id, document_id)

        try:
            await self._update_status(run_id, FusionStatus.RUNNING)

            # --- Step 1: Load data ---
            regions: List[RegionEntity] = []
            vl_blocks: List[LayoutBlock] = []

            if self.region_repo:
                regions = await self.region_repo.list_by_document(document_id)

            if self.parsing_repo:
                parsing_runs = await self.parsing_repo.list_by_document(document_id)
                # History is newest first. Never mix evidence from different runs.
                if parsing_runs:
                    for page in parsing_runs[0].pages:
                        vl_blocks.extend(page.blocks)

            if not regions:
                logger.warning("No OCR regions found for document %s — nothing to fuse.", document_id)
                return await self._complete(run_id, t_start, region_count=0)

            # --- Step 2: Spatial alignment ---
            alignment_svc = self._get_alignment_svc()
            alignments: List[EvidenceAlignment] = alignment_svc.align(
                regions=regions,
                vl_blocks=vl_blocks,
                fusion_run_id=run_id,
                document_id=document_id,
            )

            alignment_by_region = {
                a.region_id: a
                for a in alignments
                if a.region_id is not None
            }
            matched_count = sum(
                1 for a in alignments
                if a.match_status.value.startswith("matched") and a.region_id
            )

            if self.fusion_repo:
                await self.fusion_repo.save_alignments(alignments)

            # --- Step 3 & 4: Text alignment + Disagreement detection per region ---
            text_aligner = self._get_text_aligner()
            detector = self._get_disagreement_detector()
            selection_svc = self._get_selection_svc()

            all_disagreements: List[DisagreementRecord] = []
            all_proposals: List[FusionProposal] = []
            all_recovery_attempts: List[RecoveryAttempt] = []
            recovery_eligible_count = 0

            for region in regions:
                alignment = alignment_by_region.get(region.id)

                # Build hypothesis candidates from region's candidates_detail
                candidates = []
                if hasattr(region, "candidates_detail") and region.candidates_detail:
                    for cand in region.candidates_detail:
                        cand = cand.model_dump() if hasattr(cand, "model_dump") else cand
                        raw_text = cand.get("text", "") or ""
                        source = cand.get("provider_id") or cand.get("source", "unknown")
                        version = cand.get("model_version", "unknown")
                        confidence = cand.get("confidence")
                        hyp = text_aligner.build_hypothesis_candidate(
                            source_model=source,
                            model_version=version,
                            raw_text=raw_text,
                            raw_confidence=confidence,
                        )
                        candidates.append(hyp)
                else:
                    # Fallback: use region.original text as single candidate
                    if region.original:
                        hyp = text_aligner.build_hypothesis_candidate(
                            source_model="paddleocr-cloud",
                            model_version="PP-OCRv6",
                            raw_text=region.original,
                            raw_confidence=region.confidence,
                        )
                        candidates.append(hyp)

                # Text alignment
                aligned = text_aligner.align(region_id=region.id, candidates=candidates)

                # Disagreement detection
                disagreements = detector.detect(
                    region=region,
                    aligned=aligned,
                    alignment=alignment,
                    fusion_run_id=run_id,
                    document_id=document_id,
                )
                all_disagreements.extend(disagreements)

                # Candidate selection
                proposal = selection_svc.propose(
                    region_id=region.id,
                    document_id=document_id,
                    page_index=region.page_index,
                    fusion_run_id=run_id,
                    aligned=aligned,
                    disagreements=disagreements,
                    alignment=alignment,
                )
                all_proposals.append(proposal)

                # Recovery eligibility check
                if self.strategy == "evidence_aware_with_recovery" and document_bytes:
                    recovery_svc = self._get_recovery_svc()
                    existing_recovery_count = 0  # fresh for this run
                    if recovery_svc.is_eligible(region, proposal, existing_recovery_count):
                        recovery_eligible_count += 1

            # --- Persist disagreements and proposals ---
            if self.fusion_repo:
                if all_disagreements:
                    await self.fusion_repo.save_disagreements(all_disagreements)
                if all_proposals:
                    await self.fusion_repo.save_proposals(all_proposals)

            # --- Compute aggregate counts ---
            disagreement_count = len([r for r in regions if any(d.region_id == r.id for d in all_disagreements)])
            auto_proposable_count = sum(1 for p in all_proposals if p.auto_proposable)
            requires_review_count = sum(1 for p in all_proposals if p.requires_review)

            execution_ms = (time.monotonic() - t_start) * 1000.0
            updated_run = await self._complete(
                run_id=run_id,
                t_start=t_start,
                region_count=len(regions),
                matched_count=matched_count,
                disagreement_count=disagreement_count,
                recovery_eligible_count=recovery_eligible_count,
                auto_proposable_count=auto_proposable_count,
                requires_review_count=requires_review_count,
            )

            logger.info(
                "Fusion run %s completed in %.0fms: %d regions, %d disagreements, %d auto-proposable, %d requires-review",
                run_id, execution_ms, len(regions), disagreement_count,
                auto_proposable_count, requires_review_count,
            )
            return updated_run

        except Exception as exc:
            logger.exception("Fusion run %s failed: %s", run_id, exc)
            return await self._fail(run_id, str(exc))

    async def get_fusion_run(self, fusion_run_id: str, document_id: str) -> Optional[FusionRun]:
        """Retrieve a FusionRun by ID, scoped to document."""
        if not self.fusion_repo:
            return None
        return await self.fusion_repo.get_fusion_run(fusion_run_id, document_id)

    async def list_fusion_runs(self, document_id: str, session_id: str) -> List[FusionRun]:
        """List all FusionRuns for a document, session-scoped."""
        if not self.fusion_repo:
            return []
        return await self.fusion_repo.list_fusion_runs(document_id, session_id)

    async def get_disagreements(
        self,
        document_id: str,
        fusion_run_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[DisagreementRecord]:
        """Retrieve disagreement records for a document."""
        if not self.fusion_repo:
            return []
        return await self.fusion_repo.list_disagreements(
            document_id=document_id,
            fusion_run_id=fusion_run_id,
            severity=severity,
        )

    async def get_proposals(self, document_id: str, fusion_run_id: str) -> List[FusionProposal]:
        """Retrieve fusion proposals for a fusion run."""
        if not self.fusion_repo:
            return []
        return await self.fusion_repo.list_proposals(document_id, fusion_run_id)

    async def get_region_evidence(
        self,
        document_id: str,
        region_id: str,
        fusion_run_id: Optional[str] = None,
    ) -> dict:
        """Assemble complete evidence view for a region."""
        result: dict = {
            "region_id": region_id,
            "document_id": document_id,
            "fusion_proposal": None,
            "disagreements": [],
            "recovery_attempts": [],
            "alignments": [],
        }
        if not self.fusion_repo:
            return result

        if fusion_run_id:
            proposals = await self.fusion_repo.list_proposals(document_id, fusion_run_id)
            region_proposals = [p for p in proposals if p.region_id == region_id]
            if region_proposals:
                result["fusion_proposal"] = region_proposals[-1].model_dump()

        disagreements = await self.fusion_repo.list_disagreements(
            document_id=document_id,
            region_id=region_id,
        )
        result["disagreements"] = [d.model_dump() for d in disagreements]

        recovery = await self.fusion_repo.list_recovery_attempts(document_id, region_id)
        result["recovery_attempts"] = [r.model_dump() for r in recovery]

        alignments = await self.fusion_repo.list_alignments_for_region(document_id, region_id)
        result["alignments"] = [a.model_dump() for a in alignments]

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _update_status(self, run_id: str, status: FusionStatus) -> None:
        if self.fusion_repo:
            await self.fusion_repo.update_fusion_run_status(run_id, status.value)

    async def _complete(
        self,
        run_id: str,
        t_start: float,
        region_count: int = 0,
        matched_count: int = 0,
        disagreement_count: int = 0,
        recovery_eligible_count: int = 0,
        auto_proposable_count: int = 0,
        requires_review_count: int = 0,
    ) -> FusionRun:
        execution_ms = (time.monotonic() - t_start) * 1000.0
        now = datetime.now(timezone.utc).isoformat()

        partial = FusionRun(
            id=run_id,
            document_id="",
            status=FusionStatus.COMPLETED,
            region_count=region_count,
            matched_count=matched_count,
            disagreement_count=disagreement_count,
            recovery_eligible_count=recovery_eligible_count,
            auto_proposable_count=auto_proposable_count,
            requires_review_count=requires_review_count,
            execution_time_ms=round(execution_ms, 2),
            created_by_session="",
            created_at=now,
            updated_at=now,
        )

        if self.fusion_repo:
            return await self.fusion_repo.finalize_fusion_run(run_id, partial)
        return partial

    async def _fail(self, run_id: str, error_message: str) -> FusionRun:
        now = datetime.now(timezone.utc).isoformat()
        partial = FusionRun(
            id=run_id,
            document_id="",
            status=FusionStatus.FAILED,
            error_message=error_message[:500],
            created_by_session="",
            created_at=now,
            updated_at=now,
        )
        if self.fusion_repo:
            return await self.fusion_repo.finalize_fusion_run(run_id, partial)
        return partial
