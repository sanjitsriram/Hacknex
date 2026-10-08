"""Core infrastructure package: configuration, logging, errors, security, and middleware."""

from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.core.errors import EvidenceOCRError
from evidence_ocr.core.logging import get_logger

__all__ = ["Settings", "get_settings", "EvidenceOCRError", "get_logger"]
