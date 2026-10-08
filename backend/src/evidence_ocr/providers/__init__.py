"""Cloud and storage provider interfaces and mock adapters."""

from evidence_ocr.providers.ocr import (
    BaseOCRProvider,
    MockOCRProvider,
    OCRResult,
    OCRWord,
    ProviderMetadata,
)
from evidence_ocr.providers.paddleocr import PaddleOCRCloudProvider
from evidence_ocr.providers.paddleocr_vl import (
    PaddleOCRVLCloudProvider,
    ParsedDocumentResult,
)
from evidence_ocr.providers.storage import (
    BaseStorageProvider,
    MockStorageProvider,
)
from evidence_ocr.providers.trocr import TrOCRProvider
from evidence_ocr.providers.vlm import (
    BaseVLMProvider,
    MockVLMProvider,
    VLMRecoveryRequest,
    VLMResult,
)

__all__ = [
    "BaseOCRProvider",
    "MockOCRProvider",
    "PaddleOCRCloudProvider",
    "PaddleOCRVLCloudProvider",
    "ParsedDocumentResult",
    "TrOCRProvider",
    "OCRResult",
    "OCRWord",
    "ProviderMetadata",
    "BaseVLMProvider",
    "MockVLMProvider",
    "VLMRecoveryRequest",
    "VLMResult",
    "BaseStorageProvider",
    "MockStorageProvider",
]
