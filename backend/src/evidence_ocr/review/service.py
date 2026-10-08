"""Human review and verification domain service with optimistic concurrency and audit logging."""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from evidence_ocr.core.errors import EntityNotFoundError, InvalidInputError, PreconditionFailedError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.regions import RegionRepository
from evidence_ocr.models.audit import AuditEvent
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.schemas.review import (
    AuditEventResponse,
    CompleteReviewResponse,
    RegionItemResponse,
    RegionUpdateResponse,
    ReviewSessionResponse,
    TranscriptUpdateResponse,
)

logger = get_logger("evidence_ocr.review")


class ReviewService:
    """Manages reviewer modifications, optimistic concurrency revision checks, and audit trails."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        region_repo: Optional[RegionRepository] = None,
    ) -> None:
        self.doc_repo = document_repo
        self.region_repo = region_repo
        # Memory audit store for Phase 1
        self._audit_events: List[AuditEvent] = []
        self._region_decisions: Dict[str, Dict[str, str]] = {}
        self._transcripts: Dict[str, str] = {}

    async def get_review_session(self, document_id: str) -> ReviewSessionResponse:
        """Retrieve the review workspace session for a document."""
        doc = await self.doc_repo.get_by_id(document_id)
        if not doc:
            raise EntityNotFoundError("Document", document_id)

        # Baseline sample data if demo document or initialized session
        transcript = self._transcripts.get(
            document_id,
            "Site inspection · 08 October 2026\n\nArrived at the east entrance at 09:15.\nThe north wall measures 4.8 metres.\nSurface is dry; no visible cracks.\n\nFollow up with Mr. Harris on Friday.\nCheck the joints along the window.\nReplace the bracket before inspection.\n\nMaterials required:\n2 timber panels, 6 bolts, primer.\n\nNext visit: 12 October, 10:30 am.",
        )

        decisions = self._region_decisions.get(document_id, {})
        regions = []
        if self.region_repo:
            db_regions = await self.region_repo.list_by_document(document_id)
            if db_regions:
                regions = [
                    RegionItemResponse(
                        id=r.id,
                        line=r.line,
                        original=r.original,
                        alternatives=r.alternatives,
                        reason=r.reason,
                        x=r.bounding_box.x,
                        y=r.bounding_box.y,
                        w=r.bounding_box.w,
                        h=r.bounding_box.h,
                        status=r.status.value if hasattr(r.status, "value") else str(r.status),
                        decision=r.reviewer_decision,
                    )
                    for r in db_regions
                ]

        if not regions:
            regions = [
                RegionItemResponse(
                    id="r1",
                    line="The north wall measures 4.8 metres.",
                    original="4.8",
                    alternatives=["4.8", "4.3"],
                    reason="The whole-line reading and word crop disagree on the last digit.",
                    x=57.0,
                    y=29.8,
                    w=12.0,
                    h=5.0,
                    status="accepted" if "r1" in decisions else "pending",
                    decision=decisions.get("r1"),
                ),
                RegionItemResponse(
                    id="r2",
                    line="Follow up with Mr. Harris on Friday.",
                    original="Harris",
                    alternatives=["Harris", "Harvis"],
                    reason="Two recognition candidates disagree on the middle letter pair.",
                    x=46.0,
                    y=45.5,
                    w=19.0,
                    h=5.0,
                    status="accepted" if "r2" in decisions else "pending",
                    decision=decisions.get("r2"),
                ),
                RegionItemResponse(
                    id="r3",
                    line="Replace the bracket before inspection.",
                    original="bracket",
                    alternatives=["bracket", "basket"],
                    reason="Overlapping strokes reduce the legibility of this region.",
                    x=33.0,
                    y=56.0,
                    w=24.0,
                    h=5.0,
                    status="accepted" if "r3" in decisions else "pending",
                    decision=decisions.get("r3"),
                ),
            ]

        doc_events = [
            AuditEventResponse(
                id=evt.id,
                time=evt.time,
                action=evt.action,
                detail=evt.detail,
            )
            for evt in self._audit_events
            if evt.document_id == document_id
        ]

        all_resolved = len(regions) > 0 and all(r.status != "pending" for r in regions)

        return ReviewSessionResponse(
            document_id=document_id,
            transcript=transcript,
            regions=regions,
            revision=doc.revision,
            reviewed=all_resolved,
            events=doc_events,
        )

    async def update_region_decision(
        self,
        document_id: str,
        region_id: str,
        decision: str,
        is_illegible: bool,
        expected_revision: int,
        reviewer: str = "Sanjit",
    ) -> RegionUpdateResponse:
        """Update region decision with optimistic concurrency check."""
        now = datetime.now(timezone.utc).isoformat()
        updated_doc = await self.doc_repo.increment_revision(document_id, expected_revision)

        if document_id not in self._region_decisions:
            self._region_decisions[document_id] = {}
        self._region_decisions[document_id][region_id] = decision

        if self.region_repo:
            await self.region_repo.update_decision(
                document_id=document_id,
                region_id=region_id,
                decision=decision,
                is_illegible=is_illegible,
            )

        action_name = "Marked illegible" if is_illegible else "Accepted alternative"
        event = AuditEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            time=now,
            action=action_name,
            detail=f"Region {region_id} confirmed as '{decision}' by {reviewer}",
            reviewer=reviewer,
            region_id=region_id,
            new_value=decision,
            revision=updated_doc.revision,
        )
        self._audit_events.append(event)

        region_item = RegionItemResponse(
            id=region_id,
            line="Line context",
            original=decision,
            alternatives=[decision],
            reason="Confirmed by reviewer",
            x=50.0,
            y=30.0,
            w=15.0,
            h=5.0,
            status="accepted",
            decision=decision,
        )

        audit_resp = AuditEventResponse(
            id=event.id,
            time=event.time,
            action=event.action,
            detail=event.detail,
        )

        return RegionUpdateResponse(
            region=region_item,
            revision=updated_doc.revision,
            audit_event=audit_resp,
        )

    async def update_transcript(
        self,
        document_id: str,
        text: str,
        expected_revision: int,
        reviewer: str = "Sanjit",
    ) -> TranscriptUpdateResponse:
        """Update full document transcript text with optimistic concurrency check."""
        now = datetime.now(timezone.utc).isoformat()
        updated_doc = await self.doc_repo.increment_revision(document_id, expected_revision)
        self._transcripts[document_id] = text

        event = AuditEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            time=now,
            action="Manual transcript edit",
            detail=f"Full transcript updated by {reviewer}",
            reviewer=reviewer,
            revision=updated_doc.revision,
        )
        self._audit_events.append(event)

        audit_resp = AuditEventResponse(
            id=event.id,
            time=event.time,
            action=event.action,
            detail=event.detail,
        )

        return TranscriptUpdateResponse(
            text=text,
            revision=updated_doc.revision,
            audit_event=audit_resp,
        )

    async def complete_review(
        self,
        document_id: str,
        expected_revision: int,
        reviewer: str = "Sanjit",
    ) -> CompleteReviewResponse:
        """Mark review complete, rejecting if unresolved mandatory regions exist."""
        session = await self.get_review_session(document_id)
        unresolved = [r.id for r in session.regions if r.status == "pending"]
        if unresolved:
            raise InvalidInputError(
                f"Cannot complete review: mandatory regions {unresolved} are unresolved.",
                details={"unresolved_regions": unresolved},
            )

        updated_doc = await self.doc_repo.increment_revision(
            document_id, expected_revision, additional_updates={"status": DocumentStatus.REVIEWED.value}
        )

        now = datetime.now(timezone.utc).isoformat()
        event = AuditEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            time=now,
            action="Completed review",
            detail=f"Review verified and finalized by {reviewer}",
            reviewer=reviewer,
            revision=updated_doc.revision,
        )
        self._audit_events.append(event)

        return CompleteReviewResponse(
            document_id=document_id,
            status=DocumentStatus.REVIEWED.value,
            revision=updated_doc.revision,
        )
