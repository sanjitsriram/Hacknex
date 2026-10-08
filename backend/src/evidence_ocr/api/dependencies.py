"""FastAPI dependency injection providers."""

from evidence_ocr.fusion.service import FusionService
from functools import lru_cache
from typing import Annotated, Optional
from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.db.client import DatabaseManager, get_db, get_db_manager
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.db.repositories.parsing import DocumentParsingRepository
from evidence_ocr.db.repositories.regions import RegionRepository
from evidence_ocr.evaluation.service import EvaluationService
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.providers.ocr import BaseOCRProvider, MockOCRProvider
from evidence_ocr.providers.paddleocr import PaddleOCRCloudProvider
from evidence_ocr.providers.paddleocr_vl import PaddleOCRVLCloudProvider
from evidence_ocr.providers.storage import BaseStorageProvider, GridFSStorageProvider, MockStorageProvider
from evidence_ocr.providers.trocr import TrOCRProvider
from evidence_ocr.recognition.service import RecognitionService
from evidence_ocr.review.service import ReviewService
from evidence_ocr.workers.runner import WorkerRunner


def get_storage_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BaseStorageProvider:
    """Provide storage provider: GridFSStorageProvider when connected to MongoDB, or MockStorageProvider."""
    db_mgr = get_db_manager()
    if db_mgr.is_connected:
        return GridFSStorageProvider(db=db_mgr.get_database(), bucket_name=settings.gridfs_bucket_name)
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


def get_region_repository() -> Optional[RegionRepository]:
    """Provide RegionRepository instance bound to active database if connected."""
    db_mgr = get_db_manager()
    if db_mgr.is_connected:
        return RegionRepository(db_mgr.get_database())
    return None


def get_parsing_repository() -> Optional[DocumentParsingRepository]:
    """Provide DocumentParsingRepository instance bound to active database if connected."""
    db_mgr = get_db_manager()
    if db_mgr.is_connected:
        return DocumentParsingRepository(db_mgr.get_database())
    return None


# TrOCR Provider Singleton
_trocr_provider_instance: Optional[TrOCRProvider] = None
_paddleocr_provider_instance: Optional[PaddleOCRCloudProvider] = None
_paddleocr_vl_provider_instance: Optional[PaddleOCRVLCloudProvider] = None


def get_paddleocr_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaddleOCRCloudProvider:
    """Provide official PaddleOCR Cloud Provider configured with Pydantic settings."""
    global _paddleocr_provider_instance
    if _paddleocr_provider_instance is None:
        _paddleocr_provider_instance = PaddleOCRCloudProvider(
            access_token=settings.paddleocr_access_token,
            model=settings.paddleocr_model,
            base_url=settings.paddleocr_base_url,
            request_timeout=settings.paddleocr_request_timeout_seconds,
            poll_timeout=settings.paddleocr_poll_timeout_seconds,
            max_concurrent_jobs=settings.paddleocr_max_concurrent_jobs,
        )
    return _paddleocr_provider_instance


def get_paddleocr_vl_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> PaddleOCRVLCloudProvider:
    """Provide official PaddleOCR-VL Cloud Provider for document intelligence."""
    global _paddleocr_vl_provider_instance
    if _paddleocr_vl_provider_instance is None:
        _paddleocr_vl_provider_instance = PaddleOCRVLCloudProvider(
            access_token=settings.paddleocr_access_token,
            model=settings.paddleocr_vl_model,
            base_url=settings.paddleocr_base_url,
            request_timeout=settings.paddleocr_vl_request_timeout_seconds,
            poll_timeout=settings.paddleocr_vl_poll_timeout_seconds,
            max_concurrent_jobs=settings.paddleocr_vl_max_concurrent_jobs,
        )
    return _paddleocr_vl_provider_instance


def get_ocr_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BaseOCRProvider:
    """Provide TrOCR handwriting recognition provider."""
    global _trocr_provider_instance
    if _trocr_provider_instance is None:
        _trocr_provider_instance = TrOCRProvider(
            model_name="microsoft/trocr-base-handwritten",
            local_files_only=True,
        )
    return _trocr_provider_instance


def get_recognition_service(
    ocr_provider: Annotated[BaseOCRProvider, Depends(get_ocr_provider)],
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    storage: Annotated[BaseStorageProvider, Depends(get_storage_provider)],
    region_repo: Annotated[RegionRepository, Depends(get_region_repository)],
) -> RecognitionService:
    """Provide RecognitionService configured with TrOCR and database repositories."""
    return RecognitionService(
        providers=[ocr_provider],
        document_repo=doc_repo,
        storage_provider=storage,
        region_repo=region_repo,
    )


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
        max_pdf_pages=settings.max_pdf_pages,
    )


# Review Service Singleton (preserves review state across requests)
_review_service_instance: ReviewService | None = None


def get_review_service(
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    region_repo: Annotated[RegionRepository, Depends(get_region_repository)] = None,
) -> ReviewService:
    """Provide ReviewService instance."""
    global _review_service_instance
    if _review_service_instance is None:
        _review_service_instance = ReviewService(document_repo=doc_repo, region_repo=region_repo)
    else:
        _review_service_instance.doc_repo = doc_repo
        _review_service_instance.region_repo = region_repo
    return _review_service_instance


def get_worker_runner(
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    paddle_provider: Annotated[PaddleOCRCloudProvider, Depends(get_paddleocr_provider)],
    paddle_vl_provider: Annotated[PaddleOCRVLCloudProvider, Depends(get_paddleocr_vl_provider)],
    storage: Annotated[BaseStorageProvider, Depends(get_storage_provider)],
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    recognition_service: Annotated[RecognitionService, Depends(get_recognition_service)],
) -> WorkerRunner:
    """Provide WorkerRunner configured with PP-OCRv6 cloud, PaddleOCR-VL, and storage providers."""
    region_repo = get_region_repository()
    parsing_repo = get_parsing_repository()
    return WorkerRunner(
        job_repo=job_repo,
        cloud_ocr_provider=paddle_provider,
        paddle_vl_provider=paddle_vl_provider,
        storage_provider=storage,
        doc_repo=doc_repo,
        region_repo=region_repo,
        parsing_repo=parsing_repo,
        recognition_service=recognition_service,
    )


def get_fusion_repository():
    """Provide FusionRepository bound to the active database, or None if disconnected."""
    from evidence_ocr.db.repositories.fusion import FusionRepository
    db_mgr = get_db_manager()
    if db_mgr.is_connected:
        return FusionRepository(db_mgr.get_database())
    return None


def get_fusion_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> "FusionService":
    """Provide FusionService with budget controls and repository dependencies from Settings.

    All budget parameters are loaded from typed Pydantic Settings (environment variables).
    No values are hardcoded — Invariant 4 compliant.
    """
    from evidence_ocr.fusion.service import FusionService

    fusion_repo = get_fusion_repository()
    region_repo = get_region_repository()
    parsing_repo = get_parsing_repository()
    storage = get_storage_provider(settings)

    # TrOCR provider for recovery (singleton reuse)
    try:
        trocr = get_ocr_provider(settings)
    except Exception:
        trocr = None

    cost_weights = {
        "w1": settings.fusion_alignment_w1,
        "w2": settings.fusion_alignment_w2,
        "w3": settings.fusion_alignment_w3,
        "w4": settings.fusion_alignment_w4,
    }

    return FusionService(
        fusion_repo=fusion_repo,
        region_repo=region_repo,
        parsing_repo=parsing_repo,
        storage_provider=storage,
        trocr_provider=trocr,
        strategy=settings.fusion_strategy,
        max_trocr_variants=settings.fusion_max_trocr_variants,
        recovery_budget_seconds=settings.fusion_recovery_budget_seconds,
        max_cloud_escalations=settings.fusion_max_cloud_escalations,
        fusion_cost_weights=cost_weights,
    )

