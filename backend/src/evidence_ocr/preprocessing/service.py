"""Preprocessing service interface for image orientation, deskew, and contrast enhancement."""

from typing import Tuple
from evidence_ocr.core.logging import get_logger

logger = get_logger("evidence_ocr.preprocessing")


class PreprocessingService:
    """Service boundary for document image preprocessing.
    
    In Phase 1, defines the interface contracts for pipeline execution without
    prematurely loading heavy computer vision dependencies.
    """

    async def preprocess_page(self, image_bytes: bytes) -> Tuple[bytes, dict]:
        """Normalize page orientation, calculate skew angle, and enhance contrast.
        
        Returns:
            Tuple of (enhanced_image_bytes, preprocessing_metadata)
        """
        logger.debug("Preprocessing page image (%d bytes)", len(image_bytes))
        metadata = {
            "rotation_applied_degrees": 0,
            "skew_angle_detected": 0.0,
            "contrast_enhanced": False,
        }
        return image_bytes, metadata
