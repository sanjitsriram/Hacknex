"""FusionRepository: Typed async MongoDB repository for Phase 6 fusion collections."""

from typing import Any, Dict, List, Optional

from pymongo.asynchronous.database import AsyncDatabase

from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.base import BaseRepository
from evidence_ocr.models.fusion import (
    DisagreementRecord,
    EvidenceAlignment,
    FusionProposal,
    FusionRun,
    FusionStatus,
    RecoveryAttempt,
)

logger = get_logger("evidence_ocr.db.repositories.fusion")


class FusionRepository:
    """Aggregated repository managing all Phase 6 fusion collections.

    Collections:
      fusion_runs, evidence_alignments, disagreement_records,
      recovery_attempts, fusion_proposals
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._runs = BaseRepository(db, "fusion_runs")
        self._alignments = BaseRepository(db, "evidence_alignments")
        self._disagreements = BaseRepository(db, "disagreement_records")
        self._recovery = BaseRepository(db, "recovery_attempts")
        self._proposals = BaseRepository(db, "fusion_proposals")

    # ------------------------------------------------------------------
    # FusionRun
    # ------------------------------------------------------------------

    async def create_fusion_run(self, run: FusionRun) -> FusionRun:
        """Insert a new FusionRun record."""
        await self._runs.insert_one(run.model_dump())
        return run

    async def get_fusion_run(self, run_id: str, document_id: str) -> Optional[FusionRun]:
        """Fetch a FusionRun by ID, scoped to document."""
        doc = await self._runs.find_one({"id": run_id, "document_id": document_id})
        if not doc:
            return None
        return FusionRun(**doc)

    async def list_fusion_runs(self, document_id: str, session_id: str) -> List[FusionRun]:
        """List all FusionRuns for a document, session-scoped, newest first."""
        docs = await self._runs.find_many(
            {"document_id": document_id, "created_by_session": session_id},
            sort_field="created_at",
            sort_direction=-1,
            limit=50,
        )
        return [FusionRun(**d) for d in docs]

    async def update_fusion_run_status(self, run_id: str, status: str) -> None:
        """Update FusionRun status field."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await self._runs.update_one(
            {"id": run_id},
            {"$set": {"status": status, "updated_at": now}},
        )

    async def finalize_fusion_run(self, run_id: str, partial: FusionRun) -> FusionRun:
        """Update FusionRun with final counts, status, and execution time."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        updates = {
            "status": partial.status.value,
            "region_count": partial.region_count,
            "matched_count": partial.matched_count,
            "disagreement_count": partial.disagreement_count,
            "recovery_eligible_count": partial.recovery_eligible_count,
            "auto_proposable_count": partial.auto_proposable_count,
            "requires_review_count": partial.requires_review_count,
            "execution_time_ms": partial.execution_time_ms,
            "error_message": partial.error_message,
            "updated_at": now,
        }
        res = await self._runs.update_one({"id": run_id}, {"$set": updates})
        if res:
            return FusionRun(**res)
        return partial

    async def check_idempotency(
        self, document_id: str, idempotency_key: str
    ) -> Optional[FusionRun]:
        """Return an existing non-failed FusionRun for this idempotency key."""
        doc = await self._runs.find_one({
            "document_id": document_id,
            "idempotency_key": idempotency_key,
            "status": {"$nin": [FusionStatus.FAILED.value]},
        })
        if not doc:
            return None
        return FusionRun(**doc)

    # ------------------------------------------------------------------
    # Evidence Alignments
    # ------------------------------------------------------------------

    async def save_alignments(self, alignments: List[EvidenceAlignment]) -> None:
        """Bulk insert alignment records."""
        for a in alignments:
            await self._alignments.insert_one(a.model_dump())

    async def list_alignments_for_region(
        self, document_id: str, region_id: str
    ) -> List[EvidenceAlignment]:
        docs = await self._alignments.find_many(
            {"document_id": document_id, "region_id": region_id},
            sort_field="created_at",
            sort_direction=-1,
            limit=20,
        )
        return [EvidenceAlignment(**d) for d in docs]

    async def list_alignments_for_run(self, fusion_run_id: str) -> List[EvidenceAlignment]:
        docs = await self._alignments.find_many(
            {"fusion_run_id": fusion_run_id},
            sort_field="created_at",
            sort_direction=1,
            limit=1000,
        )
        return [EvidenceAlignment(**d) for d in docs]

    # ------------------------------------------------------------------
    # Disagreement Records
    # ------------------------------------------------------------------

    async def save_disagreements(self, records: List[DisagreementRecord]) -> None:
        for d in records:
            await self._disagreements.insert_one(d.model_dump())

    async def list_disagreements(
        self,
        document_id: str,
        fusion_run_id: Optional[str] = None,
        severity: Optional[str] = None,
        region_id: Optional[str] = None,
    ) -> List[DisagreementRecord]:
        query: Dict[str, Any] = {"document_id": document_id}
        if fusion_run_id:
            query["fusion_run_id"] = fusion_run_id
        if severity:
            query["severity"] = severity
        if region_id:
            query["region_id"] = region_id
        docs = await self._disagreements.find_many(
            query, sort_field="created_at", sort_direction=-1, limit=500
        )
        return [DisagreementRecord(**d) for d in docs]

    # ------------------------------------------------------------------
    # Recovery Attempts
    # ------------------------------------------------------------------

    async def save_recovery_attempt(self, attempt: RecoveryAttempt) -> RecoveryAttempt:
        await self._recovery.insert_one(attempt.model_dump())
        return attempt

    async def check_variant_duplicate(self, region_id: str, variant_hash: str) -> bool:
        """Return True if this (region_id, variant_hash) has already been attempted."""
        doc = await self._recovery.find_one({"region_id": region_id, "variant_hash": variant_hash})
        return doc is not None

    async def list_recovery_attempts(
        self, document_id: str, region_id: Optional[str] = None
    ) -> List[RecoveryAttempt]:
        query: Dict[str, Any] = {"document_id": document_id}
        if region_id:
            query["region_id"] = region_id
        docs = await self._recovery.find_many(
            query, sort_field="created_at", sort_direction=-1, limit=100
        )
        return [RecoveryAttempt(**d) for d in docs]

    async def count_recovery_attempts_for_region(self, region_id: str) -> int:
        return await self._recovery.count({"region_id": region_id})

    # ------------------------------------------------------------------
    # Fusion Proposals
    # ------------------------------------------------------------------

    async def save_proposals(self, proposals: List[FusionProposal]) -> None:
        for p in proposals:
            await self._proposals.insert_one(p.model_dump())

    async def list_proposals(
        self, document_id: str, fusion_run_id: str
    ) -> List[FusionProposal]:
        docs = await self._proposals.find_many(
            {"document_id": document_id, "fusion_run_id": fusion_run_id},
            sort_field="page_index",
            sort_direction=1,
            limit=500,
        )
        return [FusionProposal(**d) for d in docs]

    async def get_proposal_for_region(
        self, document_id: str, region_id: str, fusion_run_id: str
    ) -> Optional[FusionProposal]:
        doc = await self._proposals.find_one({
            "document_id": document_id,
            "region_id": region_id,
            "fusion_run_id": fusion_run_id,
        })
        if not doc:
            return None
        return FusionProposal(**doc)

    async def update_proposal_recovery(
        self, proposal_id: str, recovery_attempt_id: str
    ) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await self._proposals.update_one(
            {"id": proposal_id},
            {
                "$push": {"recovery_attempt_ids": recovery_attempt_id},
                "$set": {"updated_at": now},
            },
        )
