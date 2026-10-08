"""Unit tests for document page extraction and bounding box cropping."""

import io
import pytest
from PIL import Image

from evidence_ocr.core.errors import InvalidInputError
from evidence_ocr.models.region import BoundingBox
from evidence_ocr.preprocessing.cropper import (
    crop_bounding_box,
    extract_page_image,
    extract_region_crop,
)


def _create_sample_image(width: int = 200, height: int = 100) -> bytes:
    """Create a simple in-memory PNG image."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_crop_bounding_box_clamps_and_crops_correctly():
    """Verify crop_bounding_box correctly extracts percentage coordinates."""
    img = Image.new("RGB", (1000, 500), color=(200, 200, 200))
    bbox = BoundingBox(x=10.0, y=20.0, w=50.0, h=30.0)
    crop = crop_bounding_box(img, bbox)

    assert crop.size == (500, 150)
    assert crop.mode == "RGB"


def test_crop_bounding_box_handles_edge_boundaries():
    """Verify crop_bounding_box clamps cleanly at 100% boundary."""
    img = Image.new("RGB", (500, 500), color=(100, 100, 100))
    bbox = BoundingBox(x=90.0, y=90.0, w=10.0, h=10.0)
    crop = crop_bounding_box(img, bbox)

    assert crop.size == (50, 50)


def test_extract_page_image_rejects_empty_bytes():
    """Verify empty document bytes raise InvalidInputError."""
    with pytest.raises(InvalidInputError, match="empty"):
        extract_page_image(b"", "image/png", page_index=0)


def test_extract_page_image_rejects_corrupted_image():
    """Verify corrupted non-image bytes raise InvalidInputError."""
    with pytest.raises(InvalidInputError, match="Could not decode image"):
        extract_page_image(b"not-a-valid-image-stream", "image/png", page_index=0)


def test_extract_region_crop_returns_valid_png_bytes():
    """Verify extract_region_crop returns valid PNG bytes that can be opened by PIL."""
    sample_bytes = _create_sample_image(400, 200)
    bbox = BoundingBox(x=25.0, y=25.0, w=50.0, h=50.0)
    crop_bytes = extract_region_crop(sample_bytes, "image/png", bbox, page_index=0)

    assert len(crop_bytes) > 0
    cropped = Image.open(io.BytesIO(crop_bytes))
    assert cropped.size == (200, 100)
    assert cropped.format == "PNG"


def test_extract_page_image_pdf_page_out_of_bounds():
    """Verify invalid PDF page index raises InvalidInputError when file is PDF."""
    try:
        with open("sample_site_inspection.pdf", "rb") as f:
            pdf_bytes = f.read()
        with pytest.raises(InvalidInputError, match="out of bounds"):
            extract_page_image(pdf_bytes, "application/pdf", page_index=999)
    except FileNotFoundError:
        pytest.skip("sample_site_inspection.pdf not in root")
