"""Layout intelligence service interface for reading order and region segmentation."""

from typing import List, Tuple
from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.region import BoundingBox

logger = get_logger("evidence_ocr.layout")


class LayoutSegment:
    """Segment representing a single extracted line or block of text."""

    def __init__(self, segment_id: str, line_text: str, bbox: BoundingBox, order_index: int):
        self.segment_id = segment_id
        self.line_text = line_text
        self.bbox = bbox
        self.order_index = order_index


class LayoutService:
    """Service boundary for layout intelligence and line segmentation."""

    async def analyze_layout(self, image_bytes: bytes) -> List[LayoutSegment]:
        """Detect reading order, segment lines and words, and normalize coordinates."""
        logger.debug("Executing layout intelligence analysis (%d bytes)", len(image_bytes))
        # Interface placeholder for Phase 2 layout model integration
        return []
