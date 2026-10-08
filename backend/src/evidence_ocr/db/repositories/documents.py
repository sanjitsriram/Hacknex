"""Typed repository for DocumentEntity persistence."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.errors import PreconditionFailedError
from evidence_ocr.db.repositories.base import BaseRepository
from evidence_ocr.models.document import DocumentEntity, DocumentStatus


class DocumentRepository(BaseRepository):
    """Repository handling document collection queries and atomic revision increments."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, collection_name="documents")

    async def ensure_indexes(self) -> None:
        """Create indexes on documents collection for fast queries and uniqueness."""
        try:
            await self.collection.create_index([("id", 1)], unique=True)
            await self.collection.create_index([("created_at", -1)])
            await self.collection.create_index([("status", 1)])
            await self.collection.create_index([("sha256", 1)])
        except Exception as exc:
            logger.warning("Could not create indexes on documents collection: %s", exc)

    async def get_by_id(self, document_id: str) -> Optional[DocumentEntity]:
        """Fetch a document by its unique string identifier (id, document_id, or _id)."""
        doc = await self.find_one({"$or": [{"id": document_id}, {"document_id": document_id}, {"_id": document_id}]})
        if not doc:
            return None
        return DocumentEntity(**doc)

    async def create(self, document: DocumentEntity) -> DocumentEntity:
        """Insert a newly ingested document entity."""
        await self.insert_one(document.model_dump())
        return document

    async def update_status(self, document_id: str, new_status: DocumentStatus) -> Optional[DocumentEntity]:
        """Update the review/lifecycle status of a document."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": document_id},
            {"$set": {"status": new_status.value, "updated_at": now}},
        )
        if not res:
            return None
        return DocumentEntity(**res)

    async def increment_revision(
        self, document_id: str, expected_revision: int, additional_updates: Optional[Dict[str, Any]] = None
    ) -> DocumentEntity:
        """Atomically increment revision enforcing optimistic concurrency control."""
        current = await self.get_by_id(document_id)
        if not current:
            raise PreconditionFailedError(
                f"Document '{document_id}' does not exist",
                expected_revision=expected_revision,
                actual_revision=0,
            )

        if current.revision != expected_revision:
            raise PreconditionFailedError(
                f"Revision conflict for document '{document_id}': expected revision {expected_revision}, current is {current.revision}",
                expected_revision=expected_revision,
                actual_revision=current.revision,
            )

        now = datetime.now(timezone.utc).isoformat()
        set_payload = {
            "revision": expected_revision + 1,
            "updated_at": now,
        }
        if additional_updates:
            set_payload.update(additional_updates)

        updated = await self.update_one(
            {"id": document_id, "revision": expected_revision},
            {"$set": set_payload},
        )
        if not updated:
            raise PreconditionFailedError(
                f"Concurrent update conflict occurred while updating document '{document_id}'",
                expected_revision=expected_revision,
                actual_revision=current.revision,
            )

        return DocumentEntity(**updated)

    async def list_documents(
        self,
        status_filter: Optional[str] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[DocumentEntity], int]:
        """Query documents with filtering and total count."""
        query: Dict[str, Any] = {}
        if status_filter and status_filter.strip():
            query["status"] = status_filter
        if search_query and search_query.strip():
            query["name"] = {"$regex": search_query.strip(), "$options": "i"}

        items = await self.find_many(query, skip=skip, limit=limit, sort_field="created_at", sort_direction=-1)
        total = await self.count(query)
        entities = [DocumentEntity(**item) for item in items]
        return entities, total
