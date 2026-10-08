"""Document page extraction and normalized bounding box cropping."""

import io
from typing import Tuple
from PIL import Image
import pypdfium2 as pdfium

from evidence_ocr.core.errors import InvalidInputError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.region import BoundingBox

logger = get_logger("evidence_ocr.preprocessing.cropper")


def extract_page_image(document_bytes: bytes, mime_type: str, page_index: int = 0) -> Image.Image:
    """Render or decode document page bytes into a PIL RGB Image."""
    if not document_bytes:
        raise InvalidInputError("Document byte stream is empty.")

    clean_mime = (mime_type or "").lower().strip()

    if "pdf" in clean_mime:
        try:
            pdf = pdfium.PdfDocument(document_bytes)
            if page_index < 0 or page_index >= len(pdf):
                raise InvalidInputError(f"Page index {page_index} out of bounds (document has {len(pdf)} pages).")
            page = pdf[page_index]
            # Render at 200 DPI (scale ~ 2.77) for high-fidelity OCR line extraction
            bitmap = page.render(scale=2.77)
            return bitmap.to_pil().convert("RGB")
        except InvalidInputError:
            raise
        except Exception as exc:
            logger.exception("Failed to render PDF page %s: %s", page_index, exc)
            raise InvalidInputError(f"Could not render PDF document page: {exc}") from exc
    else:
        try:
            img = Image.open(io.BytesIO(document_bytes))
            return img.convert("RGB")
        except Exception as exc:
            logger.exception("Failed to decode image bytes: %s", exc)
            raise InvalidInputError(f"Could not decode image document: {exc}") from exc


def crop_bounding_box(image: Image.Image, bbox: BoundingBox) -> Image.Image:
    """Crop normalized percentage bounding box [0.0, 100.0] from a PIL Image."""
    W, H = image.size
    if W <= 0 or H <= 0:
        raise InvalidInputError(f"Invalid image dimensions: {W}x{H}")

    left = int((max(0.0, min(100.0, bbox.x)) / 100.0) * W)
    top = int((max(0.0, min(100.0, bbox.y)) / 100.0) * H)
    right = int((max(0.0, min(100.0, bbox.x + bbox.w)) / 100.0) * W)
    bottom = int((max(0.0, min(100.0, bbox.y + bbox.h)) / 100.0) * H)

    # Ensure at least 1 pixel in each dimension
    crop_w = max(1, right - left)
    crop_h = max(1, bottom - top)
    right = left + crop_w
    bottom = top + crop_h

    # Clamp to image boundary
    if right > W:
        right = W
        left = max(0, right - crop_w)
    if bottom > H:
        bottom = H
        top = max(0, bottom - crop_h)

    crop = image.crop((left, top, right, bottom))
    return crop


def extract_region_crop(
    document_bytes: bytes,
    mime_type: str,
    bbox: BoundingBox,
    page_index: int = 0,
) -> bytes:
    """Extract a region crop from document bytes and return PNG-encoded image bytes."""
    page_img = extract_page_image(document_bytes, mime_type, page_index)
    cropped_img = crop_bounding_box(page_img, bbox)

    buffer = io.BytesIO()
    cropped_img.save(buffer, format="PNG")
    return buffer.getvalue()
