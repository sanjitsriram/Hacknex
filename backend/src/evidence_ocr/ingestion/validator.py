"""Document intake validation and security inspection logic."""

import io
import os
import re
from typing import List, Optional, Tuple
import fitz
from PIL import Image, UnidentifiedImageError
from evidence_ocr.core.errors import InvalidInputError
from evidence_ocr.core.logging import get_logger

logger = get_logger("evidence_ocr.ingestion.validator")

# Supported file signatures (magic bytes)
MAGIC_SIGNATURES = {
    "application/pdf": [(0, b"%PDF-")],
    "image/png": [(0, b"\x89PNG\r\n\x1a\n")],
    "image/jpeg": [(0, b"\xff\xd8\xff")],
}

ALLOWED_EXTENSIONS = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize original filename to prevent path traversal and shell injection."""
    if not filename or not filename.strip():
        return "unnamed_document"

    # Extract base name without path components
    basename = os.path.basename(filename).replace("\\", "/").split("/")[-1]

    # Remove any directory traversal sequences
    clean = re.sub(r"(\.\./|\.\.\\)", "", basename)

    # Allow alphanumeric, dashes, underscores, dots, and spaces
    clean = re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", clean).strip()

    if not clean:
        clean = "unnamed_document"

    # Limit filename length to 150 chars
    return clean[:150]


def detect_mime_from_bytes(header: bytes) -> Optional[str]:
    """Inspect magic bytes to determine authentic MIME type."""
    if not header or len(header) < 4:
        return None

    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"

    return None


def validate_file_signature(
    header: bytes,
    content_type: Optional[str],
    filename: Optional[str],
    allowed_mimes: List[str],
) -> str:
    """Verify that file header magic bytes match declared content type and are allowed."""
    clean_name = sanitize_filename(filename)
    detected_mime = detect_mime_from_bytes(header)

    if not detected_mime:
        raise InvalidInputError(
            f"{clean_name}: invalid or unrecognizable file signature. File does not appear to be a valid PDF, PNG, or JPEG."
        )

    # Normalize allowed mimes
    normalized_allowed = [m.lower() for m in allowed_mimes]

    if detected_mime not in normalized_allowed:
        raise InvalidInputError(
            f"{clean_name}: detected file type '{detected_mime}' is not permitted. Allowed types: {', '.join(allowed_mimes)}"
        )

    # Verify that content_type provided by browser/client does not contradict detected magic bytes
    if content_type:
        norm_content_type = content_type.lower().split(";")[0].strip()
        # Allow image/jpg as alias for image/jpeg
        if norm_content_type == "image/jpg":
            norm_content_type = "image/jpeg"

        # If client provided a specific allowed mime, ensure it matches detected magic bytes
        if norm_content_type in normalized_allowed and norm_content_type != detected_mime:
            raise InvalidInputError(
                f"{clean_name}: MIME type mismatch or spoofing detected. Header declares '{content_type}' but actual byte signature is '{detected_mime}'."
            )

    # Check extension alignment if present
    ext = clean_name.rsplit(".", 1)[-1].lower() if "." in clean_name else ""
    if ext:
        expected_mime_for_ext = ALLOWED_EXTENSIONS.get(ext)
        if not expected_mime_for_ext:
            raise InvalidInputError(f"{clean_name}: unsupported file extension '.{ext}'.")
        if expected_mime_for_ext != detected_mime:
            raise InvalidInputError(
                f"{clean_name}: file extension '.{ext}' does not match actual byte signature '{detected_mime}'."
            )

    return detected_mime


def validate_document_structure(
    file_bytes: bytes,
    content_type: str,
    max_pdf_pages: int = 20,
    filename: Optional[str] = None,
) -> int:
    """Perform deep structural validation on complete file payload. Returns verified page count."""
    clean_name = sanitize_filename(filename)

    if content_type == "application/pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            logger.warning("PDF parsing failed for '%s': %s", clean_name, exc)
            raise InvalidInputError(f"{clean_name}: corrupted or malformed PDF file.") from exc

        if doc.is_encrypted:
            doc.close()
            raise InvalidInputError(f"{clean_name}: password-protected or encrypted PDFs are not supported.")

        page_count = len(doc)
        doc.close()

        if page_count < 1:
            raise InvalidInputError(f"{clean_name}: PDF document contains 0 pages.")

        if page_count > max_pdf_pages:
            raise InvalidInputError(
                f"{clean_name}: PDF exceeds maximum page limit of {max_pdf_pages} pages (has {page_count} pages)."
            )

        return page_count

    elif content_type in ["image/png", "image/jpeg", "image/webp"]:
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                img.verify()
        except (UnidentifiedImageError, SyntaxError, Exception) as exc:
            logger.warning("Image verification failed for '%s': %s", clean_name, exc)
            raise InvalidInputError(f"{clean_name}: corrupted or invalid image file.") from exc

        return 1

    else:
        raise InvalidInputError(f"{clean_name}: unsupported content type '{content_type}'.")


def validate_document_upload(
    filename: Optional[str],
    content_type: Optional[str],
    file_size_bytes: int,
    allowed_mimes: List[str],
    max_size_bytes: int,
) -> None:
    """Validate preliminary upload metadata before reading payload."""
    clean_name = sanitize_filename(filename)

    if file_size_bytes == 0:
        raise InvalidInputError(f"{clean_name}: this file is empty.")

    if file_size_bytes > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        raise InvalidInputError(f"{clean_name}: maximum file size is {max_mb} MB.")

    if content_type:
        norm_type = content_type.lower().split(";")[0].strip()
        if norm_type == "image/jpg":
            norm_type = "image/jpeg"
        if norm_type not in [m.lower() for m in allowed_mimes]:
            raise InvalidInputError(
                f"{clean_name}: unsupported file type '{content_type}'. Use a PNG, JPG, or PDF file."
            )
