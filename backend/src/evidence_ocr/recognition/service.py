"""Recognition service interface for orchestrating multi-model cloud OCR providers."""

from typing import List, Optional
from evidence_ocr.core.logging import get_logger
from evidence_ocr.providers.ocr import BaseOCRProvider, OCRResult

logger = get_logger("evidence_ocr.recognition")


class RecognitionService:
    """Orchestrates independent cloud OCR models on document pages."""

    def __init__(self, providers: Optional[List[BaseOCRProvider]] = None) -> None:
        self.providers = providers or []

    async def execute_recognition(
        self, image_bytes: bytes, language_hint: Optional[str] = None
    ) -> List[OCRResult]:
        """Run page image against registered OCR providers preserving model provenance."""
        results: List[OCRResult] = []
        for provider in self.providers:
            meta = provider.get_metadata()
            logger.info("Executing recognition with provider: %s (%s)", meta.provider_name, meta.model_version)
            res = await provider.recognize_page(image_bytes, language_hint)
            results.append(res)
        return results
