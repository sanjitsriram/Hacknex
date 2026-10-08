"""Document intake validation logic aligned with frontend constraints."""

from typing import List, Optional
from evidence_ocr.core.errors import InvalidInputError


def validate_document_upload(
    filename: Optional[str],
    content_type: Optional[str],
    file_size_bytes: int,
    allowed_mimes: List[str],
    max_size_bytes: int,
) -> None:
    """Validate uploaded document metadata and byte constraints."""
    clean_name = filename or "unnamed_file"

    if file_size_bytes == 0:
        raise InvalidInputError(f"{clean_name}: this file is empty.")

    if file_size_bytes > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        raise InvalidInputError(f"{clean_name}: maximum file size is {max_mb} MB.")

    if not content_type or content_type.lower() not in [m.lower() for m in allowed_mimes]:
        raise InvalidInputError(
            f"{clean_name}: unsupported file type '{content_type}'. Use a PNG, JPG, WebP or PDF file."
        )
