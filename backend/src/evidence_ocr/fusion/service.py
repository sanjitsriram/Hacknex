"""Evidence fusion service interface for multi-candidate alignment and targeted VLM recovery."""

from typing import List, Optional
from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.region import CandidateSuggestion, RegionEntity
from evidence_ocr.providers.ocr import OCRResult
from evidence_ocr.providers.vlm import BaseVLMProvider

logger = get_logger("evidence_ocr.fusion")


class FusionService:
    """Combines evidence from multiple OCR models and triggers targeted VLM recovery."""

    def __init__(self, vlm_provider: Optional[BaseVLMProvider] = None) -> None:
        self.vlm_provider = vlm_provider

    async def fuse_candidates(
        self, ocr_results: List[OCRResult], image_bytes: bytes
    ) -> List[RegionEntity]:
        """Align token sequences across models, detect discrepancies, and flag review regions."""
        logger.debug("Executing candidate fusion across %d model results", len(ocr_results))
        # Interface boundary for Phase 2 fusion algorithms
        return []
