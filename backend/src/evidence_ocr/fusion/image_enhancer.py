"""ImageEnhancer: Pure, side-effect-free image enhancement functions for recovery variants.

Each function takes image bytes and returns transformed image bytes without
modifying any stored originals. The original document bytes are always
preserved in GridFS as the primary evidence artifact.

Enhancements implemented:
  1. padded_crop: Expand region bbox by padding_px on each side (clamp to page boundary)
  2. clahe_gray: Convert to grayscale and apply CLAHE contrast enhancement
  3. deskewed: Detect and correct rotation skew using projection profile analysis

All transformations record their parameters for reproducibility (Invariant 3).
OpenCV (headless) is required. Graceful fallback documented if unavailable.
"""

import hashlib
import io
import math
from typing import Dict, Optional, Tuple

from PIL import Image

from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.fusion import RecoveryVariantType
from evidence_ocr.models.region import BoundingBox

logger = get_logger("evidence_ocr.fusion.image_enhancer")


def compute_sha256(image_bytes: bytes) -> str:
    """Compute SHA-256 hex digest of image bytes for deduplication."""
    return hashlib.sha256(image_bytes).hexdigest()


def _pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    """Encode PIL Image to bytes."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _bytes_to_pil(image_bytes: bytes) -> Image.Image:
    """Decode image bytes to RGB PIL Image."""
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


# ---------------------------------------------------------------------------
# Enhancement 1: Padded crop
# ---------------------------------------------------------------------------

def apply_padding(
    document_bytes: bytes,
    mime_type: str,
    bbox: BoundingBox,
    page_index: int = 0,
    padding_px: int = 4,
) -> Tuple[bytes, Dict]:
    """Expand bbox by padding_px pixels in each direction, then re-crop.

    Uses the preprocessing.cropper module to re-render at the correct scale.
    Clamps expansion to page boundary (normalized [0, 100]% space).

    Returns:
        (png_bytes, transform_params) where transform_params records the
        exact parameters used for reproducibility.
    """
    from evidence_ocr.preprocessing.cropper import extract_page_image, crop_bounding_box

    page_img = extract_page_image(document_bytes, mime_type, page_index)
    W, H = page_img.size

    # Convert padding_px to percentage
    pad_x_pct = (padding_px / max(W, 1)) * 100.0
    pad_y_pct = (padding_px / max(H, 1)) * 100.0

    padded = BoundingBox(
        x=max(0.0, bbox.x - pad_x_pct),
        y=max(0.0, bbox.y - pad_y_pct),
        w=min(100.0 - max(0.0, bbox.x - pad_x_pct), bbox.w + 2 * pad_x_pct),
        h=min(100.0 - max(0.0, bbox.y - pad_y_pct), bbox.h + 2 * pad_y_pct),
    )

    cropped = crop_bounding_box(page_img, padded)
    png_bytes = _pil_to_bytes(cropped)

    params = {
        "variant_type": RecoveryVariantType.PADDED.value,
        "padding_px": padding_px,
        "original_bbox": {"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h},
        "padded_bbox": {"x": padded.x, "y": padded.y, "w": padded.w, "h": padded.h},
        "page_dims_px": [W, H],
    }
    return png_bytes, params


# ---------------------------------------------------------------------------
# Enhancement 2: CLAHE grayscale
# ---------------------------------------------------------------------------

def apply_clahe_gray(
    crop_bytes: bytes,
    clip_limit: float = 2.0,
    tile_grid_size: Tuple[int, int] = (8, 8),
) -> Tuple[bytes, Dict]:
    """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to grayscale crop.

    Reference: Zuiderveld, K. (1994). Contrast limited adaptive histogram equalization.
    OpenCV implementation: cv2.createCLAHE(clipLimit, tileGridSize)

    The original crop_bytes are NOT modified. The enhanced image is returned
    as a new PNG-encoded byte string.

    Falls back to PIL-based histogram equalization if OpenCV is unavailable.

    Returns:
        (enhanced_png_bytes, transform_params)
    """
    params: Dict = {
        "variant_type": RecoveryVariantType.CLAHE_GRAY.value,
        "clip_limit": clip_limit,
        "tile_grid_size": list(tile_grid_size),
    }

    try:
        import cv2
        import numpy as np

        img_pil = _bytes_to_pil(crop_bytes)
        img_np = np.array(img_pil)

        # Convert to grayscale
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Apply CLAHE
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        enhanced = clahe.apply(gray)

        # Convert back to RGB for TrOCR (which expects 3-channel input)
        enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)
        enhanced_pil = Image.fromarray(enhanced_rgb)
        params["backend"] = "opencv"
        return _pil_to_bytes(enhanced_pil), params

    except ImportError:
        logger.warning("opencv-python-headless not available; using PIL histogram equalization fallback")
        img_pil = _bytes_to_pil(crop_bytes)
        gray = img_pil.convert("L")
        equalized = gray.point(lambda x: x)  # PIL has limited CLAHE support; use identity as fallback
        try:
            from PIL import ImageOps
            equalized = ImageOps.equalize(gray)
        except Exception:
            pass
        enhanced = equalized.convert("RGB")
        params["backend"] = "pillow_fallback"
        return _pil_to_bytes(enhanced), params


# ---------------------------------------------------------------------------
# Enhancement 3: Deskewing via projection profile analysis
# ---------------------------------------------------------------------------

def measure_skew_angle(crop_bytes: bytes, angle_range: float = 15.0, step: float = 0.5) -> float:
    """Estimate rotation skew angle of a handwriting crop in degrees.

    Uses horizontal projection profile variance maximization:
    - For each candidate angle in [-angle_range, +angle_range], rotate the image.
    - Compute the row-sum projection of the binarized image.
    - Select the angle that maximizes the variance of the projection
      (horizontal text lines have high variance when correctly aligned).

    Returns the estimated skew angle in degrees. Returns 0.0 if estimation fails.

    Reference: Postl, W. (1986). Detection of linear oblique structures in
    digitized documents. Proc. IAPR Int. Conf. on Pattern Recognition.
    """
    try:
        import cv2
        import numpy as np

        img_pil = _bytes_to_pil(crop_bytes)
        img_np = np.array(img_pil)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        best_angle = 0.0
        best_variance = -1.0

        angles = [angle_range - step * i for i in range(int(2 * angle_range / step) + 1)]
        h, w = binary.shape
        center = (w // 2, h // 2)

        for angle in angles:
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_NEAREST,
                                     borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            row_sums = np.sum(rotated, axis=1).astype(np.float64)
            variance = float(np.var(row_sums))
            if variance > best_variance:
                best_variance = variance
                best_angle = angle

        return best_angle
    except Exception as exc:
        logger.warning("Skew estimation failed: %s. Returning 0.0.", exc)
        return 0.0


def apply_deskew(
    crop_bytes: bytes,
    min_skew_degrees: float = 1.5,
) -> Tuple[bytes, Dict]:
    """Measure and correct document skew if angle exceeds threshold.

    Returns original bytes (with measured_angle recorded) if skew is below threshold.
    Applies rotation correction only when |angle| > min_skew_degrees.

    Returns:
        (corrected_png_bytes, transform_params)
    """
    measured_angle = measure_skew_angle(crop_bytes)
    params: Dict = {
        "variant_type": RecoveryVariantType.DESKEWED.value,
        "measured_angle_degrees": round(measured_angle, 3),
        "threshold_degrees": min_skew_degrees,
        "correction_applied": False,
    }

    if abs(measured_angle) < min_skew_degrees:
        logger.debug("Skew %.2f° below threshold %.2f°, no correction applied.", measured_angle, min_skew_degrees)
        params["correction_applied"] = False
        return crop_bytes, params

    try:
        import cv2
        import numpy as np

        img_pil = _bytes_to_pil(crop_bytes)
        img_np = np.array(img_pil)
        h, w = img_np.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, measured_angle, 1.0)
        corrected_np = cv2.warpAffine(img_np, M, (w, h),
                                      flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REPLICATE)
        corrected_pil = Image.fromarray(corrected_np)
        params["correction_applied"] = True
        return _pil_to_bytes(corrected_pil), params

    except ImportError:
        logger.warning("opencv not available for deskew rotation; returning original bytes.")
        return crop_bytes, params
    except Exception as exc:
        logger.warning("Deskew rotation failed: %s. Returning original bytes.", exc)
        return crop_bytes, params


# ---------------------------------------------------------------------------
# Variant Generation Entry Point
# ---------------------------------------------------------------------------

def generate_variants(
    document_bytes: bytes,
    mime_type: str,
    bbox: BoundingBox,
    page_index: int,
    existing_hashes: set,
    budget_remaining: int,
    original_confidence: Optional[float],
) -> list:
    """Generate ordered list of recovery variant (bytes, params, variant_type) tuples.

    Produces up to `budget_remaining` unique variants (by SHA-256 hash).
    Skips variants whose hashes are already in existing_hashes.

    Order: PADDED → CLAHE_GRAY → DESKEWED
    CLAHE is only attempted when original_confidence < 0.40.
    DESKEWED is only attempted when measured skew > 1.5°.

    Returns:
        List of dicts: {variant_type, bytes, params, sha256}
    """
    from evidence_ocr.preprocessing.cropper import extract_region_crop

    results = []

    # Get the base crop for enhancement-based variants
    try:
        base_crop = extract_region_crop(document_bytes, mime_type, bbox, page_index)
    except Exception as exc:
        logger.warning("Could not extract base crop for variants: %s", exc)
        base_crop = None

    variant_sequence = [
        RecoveryVariantType.PADDED,
        RecoveryVariantType.CLAHE_GRAY,
        RecoveryVariantType.DESKEWED,
    ]

    for vtype in variant_sequence:
        if len(results) >= budget_remaining:
            break

        try:
            if vtype == RecoveryVariantType.PADDED:
                vbytes, vparams = apply_padding(document_bytes, mime_type, bbox, page_index, padding_px=4)
            elif vtype == RecoveryVariantType.CLAHE_GRAY:
                if base_crop is None:
                    continue
                if original_confidence is not None and original_confidence >= 0.40:
                    logger.debug("Skipping CLAHE: confidence %.2f >= 0.40", original_confidence)
                    continue
                vbytes, vparams = apply_clahe_gray(base_crop)
            elif vtype == RecoveryVariantType.DESKEWED:
                if base_crop is None:
                    continue
                vbytes, vparams = apply_deskew(base_crop)
                if not vparams.get("correction_applied", False):
                    logger.debug("Skipping DESKEWED: skew below threshold")
                    continue
            else:
                continue

            sha = compute_sha256(vbytes)
            if sha in existing_hashes:
                logger.debug("Skipping duplicate variant %s (sha=%s...)", vtype.value, sha[:8])
                continue

            existing_hashes.add(sha)
            results.append({
                "variant_type": vtype,
                "bytes": vbytes,
                "params": vparams,
                "sha256": sha,
            })

        except Exception as exc:
            logger.warning("Failed to generate variant %s: %s", vtype.value, exc)
            continue

    return results
