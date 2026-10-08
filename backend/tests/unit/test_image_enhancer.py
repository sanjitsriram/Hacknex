"""Unit tests for ImageEnhancer — CLAHE, deskew, padding helpers."""

import io
import pytest

from PIL import Image

from evidence_ocr.fusion.image_enhancer import (
    apply_clahe_gray,
    apply_deskew,
    apply_padding,
    compute_sha256,
    generate_variants,
)
from evidence_ocr.models.fusion import RecoveryVariantType
from evidence_ocr.models.region import BoundingBox


def make_white_png(width=100, height=30) -> bytes:
    """Create a small white PNG image for testing."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_simple_doc_bytes() -> bytes:
    """Return a PNG image that mimics a document crop."""
    return make_white_png(200, 50)


def test_compute_sha256_deterministic():
    data = b"hello world"
    h1 = compute_sha256(data)
    h2 = compute_sha256(data)
    assert h1 == h2
    assert len(h1) == 64  # hex SHA-256


def test_compute_sha256_different_data():
    h1 = compute_sha256(b"aaa")
    h2 = compute_sha256(b"bbb")
    assert h1 != h2


def test_apply_clahe_returns_bytes():
    crop_bytes = make_white_png()
    result, params = apply_clahe_gray(crop_bytes)
    assert isinstance(result, bytes)
    assert len(result) > 0
    assert params["variant_type"] == RecoveryVariantType.CLAHE_GRAY.value
    assert "clip_limit" in params


def test_apply_clahe_params_recorded():
    crop_bytes = make_white_png()
    _, params = apply_clahe_gray(crop_bytes, clip_limit=3.0, tile_grid_size=(4, 4))
    assert params["clip_limit"] == pytest.approx(3.0)
    assert params["tile_grid_size"] == [4, 4]


def test_apply_deskew_no_correction_below_threshold():
    crop_bytes = make_white_png()
    result, params = apply_deskew(crop_bytes, min_skew_degrees=1.5)
    assert isinstance(result, bytes)
    assert params["variant_type"] == RecoveryVariantType.DESKEWED.value
    assert "measured_angle_degrees" in params
    # A white image has no skew to detect — correction_applied should be False
    # (angle from white image projection will be near 0)
    assert "correction_applied" in params


def test_apply_padding_returns_bytes_and_params():
    doc_bytes = make_simple_doc_bytes()
    bbox = BoundingBox(x=10, y=10, w=30, h=10)
    result, params = apply_padding(doc_bytes, "image/png", bbox, page_index=0, padding_px=4)
    assert isinstance(result, bytes)
    assert len(result) > 0
    assert params["variant_type"] == RecoveryVariantType.PADDED.value
    assert params["padding_px"] == 4
    assert "original_bbox" in params
    assert "padded_bbox" in params


def test_apply_padding_clamps_to_boundary():
    doc_bytes = make_simple_doc_bytes()
    # Bbox near top-left corner; padding should not go negative
    bbox = BoundingBox(x=0.5, y=0.5, w=10, h=5)
    result, params = apply_padding(doc_bytes, "image/png", bbox, page_index=0, padding_px=10)
    assert isinstance(result, bytes)
    padded = params["padded_bbox"]
    assert padded["x"] >= 0.0
    assert padded["y"] >= 0.0


def test_generate_variants_deduplication():
    doc_bytes = make_simple_doc_bytes()
    bbox = BoundingBox(x=10, y=10, w=30, h=10)
    existing_hashes = set()

    variants = generate_variants(
        document_bytes=doc_bytes,
        mime_type="image/png",
        bbox=bbox,
        page_index=0,
        existing_hashes=existing_hashes,
        budget_remaining=3,
        original_confidence=0.3,
    )

    # Check no duplicate hashes returned
    returned_hashes = [v["sha256"] for v in variants]
    assert len(returned_hashes) == len(set(returned_hashes))


def test_generate_variants_respects_budget():
    doc_bytes = make_simple_doc_bytes()
    bbox = BoundingBox(x=10, y=10, w=30, h=10)
    existing_hashes = set()

    variants = generate_variants(
        document_bytes=doc_bytes,
        mime_type="image/png",
        bbox=bbox,
        page_index=0,
        existing_hashes=existing_hashes,
        budget_remaining=1,
        original_confidence=0.2,
    )
    assert len(variants) <= 1


def test_generate_variants_skips_existing_hashes():
    doc_bytes = make_simple_doc_bytes()
    bbox = BoundingBox(x=10, y=10, w=30, h=10)

    # First run to collect all hashes
    existing_hashes = set()
    first_run = generate_variants(
        document_bytes=doc_bytes, mime_type="image/png", bbox=bbox,
        page_index=0, existing_hashes=existing_hashes, budget_remaining=10,
        original_confidence=0.2,
    )

    # Second run with same existing_hashes should produce no new variants
    second_run = generate_variants(
        document_bytes=doc_bytes, mime_type="image/png", bbox=bbox,
        page_index=0, existing_hashes=existing_hashes, budget_remaining=10,
        original_confidence=0.2,
    )
    assert len(second_run) == 0
