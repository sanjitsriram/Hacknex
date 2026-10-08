"""Generic base repository for PyMongo Async collections."""

from typing import Any, Dict, List, Optional
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from evidence_ocr.core.errors import DatabaseUnavailableError
from evidence_ocr.core.logging import get_logger

logger = get_logger("evidence_ocr.db.repository")


class BaseRepository:
    """Base repository providing standardized async MongoDB operations."""

    def __init__(self, db: AsyncDatabase, collection_name: str) -> None:
        self.db = db
        self.collection_name = collection_name

    @property
    def collection(self) -> AsyncCollection:
        """Return the bound AsyncCollection."""
        return self.db[self.collection_name]

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document matching query."""
        try:
            return await self.collection.find_one(query)
        except PyMongoError as exc:
            logger.error("Error in %s.find_one: %s", self.collection_name, str(exc))
            raise DatabaseUnavailableError(f"Database query failed: {str(exc)}") from exc

    async def find_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Find document by custom 'id' or '_id' field."""
        return await self.find_one({"id": entity_id})

    async def insert_one(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a single document."""
        try:
            # Shallow copy to avoid mutating caller's dict
            doc_to_insert = dict(document)
            if "_id" not in doc_to_insert and "id" in doc_to_insert:
                doc_to_insert["_id"] = doc_to_insert["id"]
            await self.collection.insert_one(doc_to_insert)
            return document
        except PyMongoError as exc:
            logger.error("Error in %s.insert_one: %s", self.collection_name, str(exc))
            raise DatabaseUnavailableError(f"Database insert failed: {str(exc)}") from exc

    async def update_one(
        self, query: Dict[str, Any], update_ops: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Apply update operations to a single matching document."""
        try:
            result = await self.collection.update_one(query, update_ops)
            if result.matched_count == 0:
                return None
            return await self.find_one(query)
        except PyMongoError as exc:
            logger.error("Error in %s.update_one: %s", self.collection_name, str(exc))
            raise DatabaseUnavailableError(f"Database update failed: {str(exc)}") from exc

    async def find_many(
        self,
        query: Dict[str, Any],
        skip: int = 0,
        limit: int = 50,
        sort_field: str = "created_at",
        sort_direction: int = -1,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents matching query with pagination."""
        try:
            cursor = self.collection.find(query).sort(sort_field, sort_direction).skip(skip).limit(limit)
            items = []
            async for doc in cursor:
                # Remove MongoDB _id if it mirrors id
                if "_id" in doc and "id" in doc and str(doc["_id"]) == str(doc["id"]):
                    del doc["_id"]
                items.append(doc)
            return items
        except PyMongoError as exc:
            logger.error("Error in %s.find_many: %s", self.collection_name, str(exc))
            raise DatabaseUnavailableError(f"Database query failed: {str(exc)}") from exc

    async def count(self, query: Dict[str, Any]) -> int:
        """Count documents matching query."""
        try:
            return await self.collection.count_documents(query)
        except PyMongoError as exc:
            logger.error("Error in %s.count: %s", self.collection_name, str(exc))
            raise DatabaseUnavailableError(f"Database count failed: {str(exc)}") from exc
