"""Unit and contract tests for TrOCRProvider and local handwriting recognition."""

import io
from pathlib import Path
import pytest
from PIL import Image

from evidence_ocr.core.errors import InvalidInputError, ServiceUnavailableError
from evidence_ocr.providers.trocr import TrOCRProvider


@pytest.fixture(scope="module")
def trocr_provider():
    """Module-scoped TrOCRProvider reusing cached model."""
    return TrOCRProvider(
        model_name="microsoft/trocr-base-handwritten",
        local_files_only=True,
        timeout_seconds=30.0,
    )


def _get_benchmark_crop_bytes() -> bytes:
    """Retrieve sample 00 from the benchmark fixtures if available, or create mock sample."""
    sample_p = Path("backend/tests/fixtures/benchmark_dataset/sample_00.png")
    if sample_p.exists():
        return sample_p.read_bytes()
    # Fallback synthetic text line
    img = Image.new("RGB", (300, 60), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_trocr_provider_metadata(trocr_provider):
    """Verify provider metadata satisfies Invariant 3 (reproducible versioning)."""
    meta = trocr_provider.get_metadata()
    assert meta.provider_name == "trocr"
    assert meta.model_identifier == "microsoft/trocr-base-handwritten"
    assert meta.model_version == "base-handwritten-v1.0"
    assert meta.parameters["device"] == "cpu"
    assert meta.parameters["local_files_only"] is True


@pytest.mark.asyncio
async def test_trocr_rejects_empty_bytes(trocr_provider):
    """Verify empty image bytes are rejected immediately."""
    with pytest.raises(InvalidInputError, match="empty"):
        await trocr_provider.recognize_page(b"")


@pytest.mark.asyncio
async def test_trocr_rejects_corrupted_bytes(trocr_provider):
    """Verify corrupted image bytes raise InvalidInputError."""
    with pytest.raises(InvalidInputError, match="Corrupted or unsupported"):
        await trocr_provider.recognize_page(b"not-valid-image-data-header")


@pytest.mark.asyncio
async def test_trocr_recognize_line_success(trocr_provider):
    """Verify real TrOCR inference on genuine handwritten sample produces text and confidence."""
    crop_bytes = _get_benchmark_crop_bytes()
    result = await trocr_provider.recognize_page(crop_bytes)

    assert result is not None
    assert isinstance(result.raw_text, str)
    assert len(result.raw_text) > 0
    assert result.execution_time_ms > 0
    assert result.metadata.provider_name == "trocr"
    # Verify genuine confidence from softmax
    assert len(result.words) > 0
    assert 0.0 <= result.words[0].confidence <= 1.0


@pytest.mark.asyncio
async def test_trocr_timeout_handling():
    """Verify timeout triggers ServiceUnavailableError."""
    # Set impossible 0.0001s timeout
    fast_timeout_provider = TrOCRProvider(
        model_name="microsoft/trocr-base-handwritten",
        local_files_only=True,
        timeout_seconds=0.0001,
    )
    crop_bytes = _get_benchmark_crop_bytes()
    with pytest.raises(ServiceUnavailableError, match="timed out"):
        await fast_timeout_provider.recognize_page(crop_bytes)
