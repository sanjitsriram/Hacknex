"""Typed repository for RegionEntity persistence and candidate provenance tracking."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.base import BaseRepository
from evidence_ocr.models.region import CandidateSuggestion, RegionEntity, RegionReviewStatus

logger = get_logger("evidence_ocr.db.repositories.regions")


class RegionRepository(BaseRepository):
    """Repository handling document region entities, line crops, and model candidates."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, collection_name="regions")

    async def ensure_indexes(self) -> None:
        """Create indexes for document-scoped region queries and bounding box searches."""
        try:
            await self.collection.create_index([("document_id", 1), ("id", 1)], unique=True)
            await self.collection.create_index([("document_id", 1), ("page_index", 1)])
            await self.collection.create_index([("status", 1)])
        except Exception as exc:
            logger.warning("Could not create indexes on regions collection: %s", exc)

    async def get_by_id(self, document_id: str, region_id: str) -> Optional[RegionEntity]:
        """Fetch a specific region by document ID and region ID."""
        doc = await self.find_one({"document_id": document_id, "id": region_id})
        if not doc:
            return None
        return RegionEntity(**doc)

    async def list_by_document(self, document_id: str) -> List[RegionEntity]:
        """List all extracted regions for a document."""
        items = await self.find_many(
            {"document_id": document_id},
            sort_field="page_index",
            sort_direction=1,
            limit=500,
        )
        return [RegionEntity(**item) for item in items]

    async def save_or_update(self, region: RegionEntity) -> RegionEntity:
        """Upsert a region entity by composite document_id and region id."""
        payload = region.model_dump()
        payload["_id"] = f"{region.document_id}:{region.id}"
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        await self.update_one(
            {"document_id": region.document_id, "id": region.id},
            {"$set": payload},
            upsert=True,
        )
        return region

    async def bulk_save_regions(self, document_id: str, regions: List[RegionEntity]) -> int:
        """Upsert a list of detected regions for a document preserving existing human reviews."""
        if not regions:
            return 0
        saved_count = 0
        now = datetime.now(timezone.utc).isoformat()
        for region in regions:
            payload = region.model_dump()
            payload["_id"] = f"{document_id}:{region.id}"
            payload["updated_at"] = now
            # Do NOT overwrite existing human review decisions if already reviewed
            existing = await self.get_by_id(document_id, region.id)
            if existing and existing.status != RegionReviewStatus.PENDING:
                payload["status"] = existing.status.value
                payload["reviewer_decision"] = existing.reviewer_decision
                payload["is_illegible"] = existing.is_illegible
            
            await self.update_one(
                {"document_id": document_id, "id": region.id},
                {"$set": payload},
                upsert=True,
            )
            saved_count += 1
        return saved_count

    async def add_candidate(
        self,
        document_id: str,
        region_id: str,
        candidate: CandidateSuggestion,
    ) -> Optional[RegionEntity]:
        """Append a new OCR/VLM candidate suggestion preserving model provenance."""
        now = datetime.now(timezone.utc).isoformat()
        candidate_dict = candidate.model_dump()
        
        # Add candidate to candidates_detail and text to alternatives if not present
        await self.collection.update_one(
            {"document_id": document_id, "id": region_id},
            {
                "$push": {"candidates_detail": candidate_dict},
                "$addToSet": {"alternatives": candidate.text},
                "$set": {"updated_at": now},
            },
        )
        return await self.get_by_id(document_id, region_id)

    async def update_decision(
        self,
        document_id: str,
        region_id: str,
        decision: Optional[str] = None,
        is_illegible: bool = False,
    ) -> Optional[RegionEntity]:
        """Update reviewer decision on a region."""
        now = datetime.now(timezone.utc).isoformat()
        status = RegionReviewStatus.ILLEGIBLE if is_illegible else (
            RegionReviewStatus.ACCEPTED if decision else RegionReviewStatus.PENDING
        )
        update_doc: Dict[str, Any] = {
            "status": status.value,
            "is_illegible": is_illegible,
            "updated_at": now,
        }
        if decision is not None:
            update_doc["reviewer_decision"] = decision

        await self.collection.update_one(
            {"document_id": document_id, "id": region_id},
            {"$set": update_doc},
        )
        return await self.get_by_id(document_id, region_id)
