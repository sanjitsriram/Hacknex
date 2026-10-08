"""Document ingestion domain service with GridFS streaming and compensating rollback."""

import hashlib
import io
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import UploadFile
from evidence_ocr.core.errors import DatabaseOperationError, InvalidInputError, StorageOperationError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.ingestion.validator import (
    sanitize_filename,
    validate_document_structure,
    validate_document_upload,
    validate_file_signature,
)
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.providers.storage import BaseStorageProvider

logger = get_logger("evidence_ocr.ingestion")


class IngestionService:
    """Coordinates document ingestion, incremental streaming, GridFS storage, and metadata persistence."""

    def __init__(
        self,
        document_repo: DocumentRepository,
        storage_provider: BaseStorageProvider,
        allowed_mimes: List[str],
        max_size_bytes: int,
        max_pdf_pages: int = 20,
    ) -> None:
        self.doc_repo = document_repo
        self.storage = storage_provider
        self.allowed_mimes = allowed_mimes
        self.max_size_bytes = max_size_bytes
        self.max_pdf_pages = max_pdf_pages

    async def ingest_upload(
        self,
        file: UploadFile,
        title: str = "Untitled document",
        kind: str = "Field notes",
        language: str = "English",
    ) -> DocumentEntity:
        """Stream UploadFile incrementally, enforce limits, validate integrity, and persist to GridFS + MongoDB."""
        clean_title = title.strip() if title else ""
        if not clean_title:
            raise InvalidInputError("Document title cannot be empty.")

        clean_filename = sanitize_filename(file.filename)
        sha256_hasher = hashlib.sha256()
        total_bytes = 0
        chunk_size = 64 * 1024  # 64 KiB chunks

        # Spool file to avoid keeping large payloads entirely in memory
        with tempfile.NamedTemporaryFile(delete=True) as spooled_file:
            # Read first chunk to inspect magic bytes signature
            first_chunk = await file.read(chunk_size)
            if not first_chunk:
                raise InvalidInputError(f"{clean_filename}: this file is empty.")

            total_bytes += len(first_chunk)
            if total_bytes > self.max_size_bytes:
                max_mb = self.max_size_bytes // (1024 * 1024)
                raise InvalidInputError(f"{clean_filename}: maximum file size is {max_mb} MB.")

            sha256_hasher.update(first_chunk)
            spooled_file.write(first_chunk)

            # Validate magic bytes against declared MIME type
            verified_mime = validate_file_signature(
                header=first_chunk,
                content_type=file.content_type,
                filename=clean_filename,
                allowed_mimes=self.allowed_mimes,
            )

            # Incrementally read remaining chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > self.max_size_bytes:
                    max_mb = self.max_size_bytes // (1024 * 1024)
                    raise InvalidInputError(f"{clean_filename}: maximum file size is {max_mb} MB.")
                sha256_hasher.update(chunk)
                spooled_file.write(chunk)

            spooled_file.flush()
            spooled_file.seek(0)
            file_bytes = spooled_file.read()

        sha256_hash = sha256_hasher.hexdigest()

        # Perform deep structural validation (page count, encryption, corruption)
        page_count = validate_document_structure(
            file_bytes=file_bytes,
            content_type=verified_mime,
            max_pdf_pages=self.max_pdf_pages,
            filename=clean_filename,
        )

        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        storage_filename = f"{doc_id}_{clean_filename}"

        # Step 1: Upload binary to GridFS
        gridfs_metadata = {
            "document_id": doc_id,
            "original_filename": clean_filename,
            "content_type": verified_mime,
            "sha256": sha256_hash,
            "page_count": page_count,
        }
        gridfs_file_id = await self.storage.upload(
            key=storage_filename,
            data=file_bytes,
            content_type=verified_mime,
            metadata=gridfs_metadata,
        )

        # Step 2: Formulate document entity
        now = datetime.now(timezone.utc).isoformat()
        size_kb = total_bytes / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb / 1024):.1f} MB"
        source_url = f"/api/v1/documents/{doc_id}/file"

        entity = DocumentEntity(
            id=doc_id,
            document_id=doc_id,
            name=clean_title,
            original_filename=clean_filename,
            content_type=verified_mime,
            file_size_bytes=total_bytes,
            sha256=sha256_hash,
            gridfs_file_id=gridfs_file_id,
            page_count=page_count,
            pages=page_count,
            kind=kind,
            language=language,
            status=DocumentStatus.READY_FOR_BACKEND,
            processing_status="Ready for backend",
            schema_version=1,
            added=now,
            size=size_str,
            sample=False,
            file_key=f"gridfs:evidence_files:{gridfs_file_id}",
            mime=verified_mime,
            source_url=source_url,
            revision=1,
            upload_timestamp=now,
            created_at=now,
            updated_at=now,
        )

        # Step 3: Persist document metadata in MongoDB Atlas with compensating recovery
        try:
            await self.doc_repo.create(entity)
            logger.info(
                "Ingested document '%s' (id=%s, size=%d bytes, pages=%d, sha256=%s, gridfs_id=%s)",
                entity.name,
                doc_id,
                total_bytes,
                page_count,
                sha256_hash[:8],
                gridfs_file_id,
            )
            return entity
        except Exception as exc:
            logger.critical(
                "Metadata persistence failed for document '%s' (%s). Initiating compensating cleanup of GridFS file %s: %s",
                doc_id,
                entity.name,
                gridfs_file_id,
                exc,
            )
            # COMPENSATING TRANSACTION: Delete orphaned GridFS file
            try:
                cleanup_success = await self.storage.delete(gridfs_file_id)
                if cleanup_success:
                    logger.info("Successfully cleaned up orphaned GridFS file %s after metadata failure.", gridfs_file_id)
                else:
                    logger.warning("GridFS cleanup reported false for orphaned file %s.", gridfs_file_id)
            except Exception as cleanup_exc:
                logger.error("Failed to cleanup orphaned GridFS file %s: %s", gridfs_file_id, cleanup_exc)

            raise DatabaseOperationError(f"Failed to persist document metadata: {str(exc)}") from exc

    async def ingest_document(
        self,
        title: str,
        kind: str,
        language: str,
        filename: Optional[str],
        content_type: Optional[str],
        file_bytes: bytes,
    ) -> DocumentEntity:
        """Validate and ingest raw bytes into GridFS and MongoDB (backwards-compatible programmatic intake)."""
        clean_title = title.strip() if title else ""
        if not clean_title:
            raise InvalidInputError("Document title cannot be empty.")

        clean_filename = sanitize_filename(filename)
        total_bytes = len(file_bytes)

        if total_bytes == 0:
            raise InvalidInputError(f"{clean_filename}: this file is empty.")

        if total_bytes > self.max_size_bytes:
            max_mb = self.max_size_bytes // (1024 * 1024)
            raise InvalidInputError(f"{clean_filename}: maximum file size is {max_mb} MB.")

        verified_mime = validate_file_signature(
            header=file_bytes[:1024],
            content_type=content_type,
            filename=clean_filename,
            allowed_mimes=self.allowed_mimes,
        )

        page_count = validate_document_structure(
            file_bytes=file_bytes,
            content_type=verified_mime,
            max_pdf_pages=self.max_pdf_pages,
            filename=clean_filename,
        )

        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        storage_filename = f"{doc_id}_{clean_filename}"

        gridfs_metadata = {
            "document_id": doc_id,
            "original_filename": clean_filename,
            "content_type": verified_mime,
            "sha256": sha256_hash,
            "page_count": page_count,
        }
        gridfs_file_id = await self.storage.upload(
            key=storage_filename,
            data=file_bytes,
            content_type=verified_mime,
            metadata=gridfs_metadata,
        )

        now = datetime.now(timezone.utc).isoformat()
        size_kb = total_bytes / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb / 1024):.1f} MB"
        source_url = f"/api/v1/documents/{doc_id}/file"

        entity = DocumentEntity(
            id=doc_id,
            document_id=doc_id,
            name=clean_title,
            original_filename=clean_filename,
            content_type=verified_mime,
            file_size_bytes=total_bytes,
            sha256=sha256_hash,
            gridfs_file_id=gridfs_file_id,
            page_count=page_count,
            pages=page_count,
            kind=kind,
            language=language,
            status=DocumentStatus.READY_FOR_BACKEND,
            processing_status="Ready for backend",
            schema_version=1,
            added=now,
            size=size_str,
            sample=False,
            file_key=f"gridfs:evidence_files:{gridfs_file_id}",
            mime=verified_mime,
            source_url=source_url,
            revision=1,
            upload_timestamp=now,
            created_at=now,
            updated_at=now,
        )

        try:
            await self.doc_repo.create(entity)
            logger.info("Successfully ingested document '%s' (%s, %d bytes)", doc_id, entity.name, total_bytes)
            return entity
        except Exception as exc:
            logger.critical(
                "Metadata persistence failed for '%s'. Cleaning up orphaned GridFS file %s: %s",
                doc_id,
                gridfs_file_id,
                exc,
            )
            try:
                await self.storage.delete(gridfs_file_id)
            except Exception as cleanup_exc:
                logger.error("Compensating cleanup failed for GridFS file %s: %s", gridfs_file_id, cleanup_exc)
            raise DatabaseOperationError(f"Failed to persist document metadata: {str(exc)}") from exc
