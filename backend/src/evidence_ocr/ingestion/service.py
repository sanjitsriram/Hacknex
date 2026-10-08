"""Document ingestion domain service."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from evidence_ocr.core.errors import InvalidInputError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.providers.storage import BaseStorageProvider
from evidence_ocr.ingestion.validator import validate_document_upload

logger = get_logger("evidence_ocr.ingestion")


class IngestionService:
    """Coordinates document ingestion, file storage, and initial entity persistence."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        storage_provider: BaseStorageProvider,
        allowed_mimes: List[str],
        max_size_bytes: int,
    ) -> None:
        self.doc_repo = document_repo
        self.storage = storage_provider
        self.allowed_mimes = allowed_mimes
        self.max_size_bytes = max_size_bytes

    async def ingest_document(
        self,
        title: str,
        kind: str,
        language: str,
        filename: Optional[str],
        content_type: Optional[str],
        file_bytes: bytes,
    ) -> DocumentEntity:
        """Validate, store, and persist a new document entity."""
        if not title or not title.strip():
            raise InvalidInputError("Document title cannot be empty.")

        validate_document_upload(
            filename=filename,
            content_type=content_type,
            file_size_bytes=len(file_bytes),
            allowed_mimes=self.allowed_mimes,
            max_size_bytes=self.max_size_bytes,
        )

        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        storage_key = f"originals/{doc_id}/{filename or 'original'}"
        await self.storage.upload(storage_key, file_bytes, content_type or "application/octet-stream")
        source_url = await self.storage.generate_access_url(storage_key)

        now = datetime.now(timezone.utc).isoformat()
        size_kb = len(file_bytes) / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb / 1024):.1f} MB"

        entity = DocumentEntity(
            id=doc_id,
            name=title.strip(),
            kind=kind,
            language=language,
            pages=1,
            status=DocumentStatus.NEEDS_REVIEW,
            added=now,
            size=size_str,
            sample=False,
            file_key=storage_key,
            mime=content_type,
            source_url=source_url,
            revision=1,
            created_at=now,
            updated_at=now,
        )

        await self.doc_repo.create(entity)
        logger.info("Successfully ingested document '%s' (%s, %d bytes)", doc_id, entity.name, len(file_bytes))
        return entity
