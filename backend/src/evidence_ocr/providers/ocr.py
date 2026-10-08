"""Abstract provider interfaces and mock implementations for cloud OCR models."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProviderMetadata(BaseModel):
    """Execution metadata ensuring model version reproducibility."""

    provider_name: str = Field(description="Cloud provider identifier")
    model_identifier: str = Field(description="Model family or name")
    model_version: str = Field(description="Pinned model version or snapshot tag")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Inference parameters (temperature=0.0, etc.)")


class OCRWord(BaseModel):
    """Individual recognized token with coordinates and confidence."""

    text: str = Field(description="Recognized token text")
    confidence: float = Field(ge=0.0, le=1.0, description="Provider raw confidence score")
    bounding_box: Dict[str, float] = Field(description="Normalized coordinates {x, y, w, h}")


class DetectedRegion(BaseModel):
    """Normalized detected text line/block region with polygon, box, text, and confidence."""

    text: str = Field(description="Extracted text string")
    confidence: float = Field(ge=0.0, le=1.0, description="Raw model confidence score")
    bounding_box: Dict[str, float] = Field(description="Normalized percentage coordinates {x, y, w, h}")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="Original unrotated detected polygon vertices in pixel coordinates"
    )
    page_index: int = Field(default=0, ge=0, description="Page index (0-indexed)")
    is_illegible: bool = Field(default=False, description="Flag indicating low confidence or illegibility")


class OCRResult(BaseModel):
    """Normalized output from an OCR engine."""

    raw_text: str = Field(description="Full extracted text sequence")
    words: List[OCRWord] = Field(default_factory=list, description="Extracted word tokens with locations")
    detected_regions: List[DetectedRegion] = Field(
        default_factory=list, description="Document-level detected text regions with polygons"
    )
    metadata: ProviderMetadata = Field(description="Provider version metadata")
    execution_time_ms: float = Field(ge=0.0, description="Provider latency in milliseconds")


class BaseOCRProvider(ABC):
    """Abstract interface for external OCR recognition engines."""

    @abstractmethod
    def get_metadata(self) -> ProviderMetadata:
        """Return provider and model versioning metadata."""
        pass

    @abstractmethod
    async def recognize_page(
        self, image_bytes: bytes, language_hint: Optional[str] = None
    ) -> OCRResult:
        """Execute OCR recognition on a single page image."""
        pass

    async def recognize_document(
        self,
        document_bytes: bytes,
        mime_type: str = "application/pdf",
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        """Execute document-level OCR and region detection across pages."""
        return await self.recognize_page(document_bytes, language_hint)


class MockOCRProvider(BaseOCRProvider):
    """In-memory mock provider used for contract validation without external dependencies."""

    def __init__(self, model_version: str = "mock-v1.0") -> None:
        self.version = model_version

    def get_metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_name="mock-ocr",
            model_identifier="mock-handwriting-engine",
            model_version=self.version,
            parameters={"temperature": 0.0},
        )

    async def recognize_page(
        self, image_bytes: bytes, language_hint: Optional[str] = None
    ) -> OCRResult:
        return OCRResult(
            raw_text="Site inspection · Sample mock transcript",
            words=[
                OCRWord(text="Site", confidence=0.98, bounding_box={"x": 10.0, "y": 10.0, "w": 8.0, "h": 3.0}),
                OCRWord(text="inspection", confidence=0.95, bounding_box={"x": 20.0, "y": 10.0, "w": 18.0, "h": 3.0}),
            ],
            metadata=self.get_metadata(),
            execution_time_ms=12.5,
        )
