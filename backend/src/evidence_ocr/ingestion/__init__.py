"""Document ingestion package."""

from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.ingestion.validator import validate_document_upload

__all__ = ["IngestionService", "validate_document_upload"]
