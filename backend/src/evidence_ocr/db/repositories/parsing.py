"""Typed repository for DocumentParsingRun persistence and layout retrieval."""

from typing import List, Optional
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.base import BaseRepository
from evidence_ocr.models.parsing import DocumentParsingRun

logger = get_logger("evidence_ocr.db.repositories.parsing")


class DocumentParsingRepository(BaseRepository):
    """Repository handling PaddleOCR-VL document parsing runs, layout blocks, and Markdown."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, collection_name="document_parsing_runs")

    async def ensure_indexes(self) -> None:
        """Create indexes for document-scoped parsing run queries."""
        try:
            await self.collection.create_index([("id", 1)], unique=True)
            await self.collection.create_index([("document_id", 1), ("created_at", -1)])
            await self.collection.create_index([("job_id", 1)])
        except Exception as exc:
            logger.warning("Could not create indexes on document_parsing_runs collection: %s", exc)

    async def save_run(self, run: DocumentParsingRun) -> DocumentParsingRun:
        """Persist or replace a document parsing run."""
        payload = run.model_dump()
        payload["_id"] = run.id
        await self.update_one(
            {"id": run.id},
            {"$set": payload},
            upsert=True,
        )
        return run

    async def get_by_id(self, run_id: str) -> Optional[DocumentParsingRun]:
        """Fetch a specific parsing run by run ID."""
        doc = await self.find_one({"id": run_id})
        if not doc:
            return None
        return DocumentParsingRun(**doc)

    async def get_latest_by_document(self, document_id: str) -> Optional[DocumentParsingRun]:
        """Retrieve the most recent successful parsing run for a document."""
        items = await self.find_many(
            {"document_id": document_id},
            sort_field="created_at",
            sort_direction=-1,
            limit=1,
        )
        if not items:
            return None
        return DocumentParsingRun(**items[0])

    async def list_by_document(self, document_id: str, limit: int = 20) -> List[DocumentParsingRun]:
        """List historical document parsing runs for a document."""
        items = await self.find_many(
            {"document_id": document_id},
            sort_field="created_at",
            sort_direction=-1,
            limit=limit,
        )
        return [DocumentParsingRun(**item) for item in items]
