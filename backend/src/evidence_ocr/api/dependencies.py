"""FastAPI dependency injection providers."""

from functools import lru_cache
from typing import Annotated
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.db.client import DatabaseManager, get_db, get_db_manager
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.evaluation.service import EvaluationService
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.providers.storage import BaseStorageProvider, MockStorageProvider
from evidence_ocr.review.service import ReviewService
from evidence_ocr.workers.runner import WorkerRunner


# Storage Provider Singleton
@lru_cache(maxsize=1)
def get_storage_provider() -> BaseStorageProvider:
    """Return storage provider instance."""
    return MockStorageProvider()


# Evaluation Service Singleton
@lru_cache(maxsize=1)
def get_evaluation_service() -> EvaluationService:
    """Return evaluation service instance."""
    return EvaluationService()


def get_document_repository(db: Annotated[AsyncDatabase, Depends(get_db)]) -> DocumentRepository:
    """Provide DocumentRepository instance bound to the active database."""
    return DocumentRepository(db)


def get_job_repository(db: Annotated[AsyncDatabase, Depends(get_db)]) -> JobRepository:
    """Provide JobRepository instance bound to the active database."""
    return JobRepository(db)


def get_ingestion_service(
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    storage: Annotated[BaseStorageProvider, Depends(get_storage_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> IngestionService:
    """Provide IngestionService configured with settings."""
    return IngestionService(
        document_repo=doc_repo,
        storage_provider=storage,
        allowed_mimes=settings.allowed_mime_types,
        max_size_bytes=settings.max_upload_size_bytes,
    )


# Review Service Singleton (preserves review state across requests in Phase 1)
_review_service_instance: ReviewService | None = None


def get_review_service(
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
) -> ReviewService:
    """Provide ReviewService instance."""
    global _review_service_instance
    if _review_service_instance is None:
        _review_service_instance = ReviewService(document_repo=doc_repo)
    else:
        _review_service_instance.doc_repo = doc_repo
    return _review_service_instance


def get_worker_runner(
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> WorkerRunner:
    """Provide WorkerRunner instance."""
    return WorkerRunner(job_repo=job_repo)
