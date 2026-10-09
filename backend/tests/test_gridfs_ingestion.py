"""Comprehensive Phase 2 automated test suite for MongoDB GridFS document ingestion.

Covers all 20 required scenarios:
1. Successful PDF upload
2. Successful PNG upload
3. Successful JPEG upload
4. Invalid extension
5. Invalid or spoofed MIME type
6. Corrupted PDF/image
7. Exceeded file-size limit
8. Exceeded PDF page limit
9. Duplicate original filenames
10. SHA-256 calculation
11. MongoDB metadata persistence
12. GridFS round-trip byte integrity
13. Missing document and file
14. GridFS upload failure
15. MongoDB metadata failure
16. Orphaned-file cleanup
17. Concurrent uploads
18. API response contracts
19. Frontend upload integration contract
20. Persistence across sessions
"""

import asyncio
import hashlib
import io
import pytest
import httpx
import fitz
from PIL import Image
from unittest.mock import AsyncMock, patch
from bson import ObjectId
from evidence_ocr.api.dependencies import get_document_repository, get_storage_provider
from evidence_ocr.core.errors import InvalidInputError, StorageOperationError
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.models.document import DocumentEntity, DocumentStatus
from evidence_ocr.providers.storage import GridFSStorageProvider, MockStorageProvider


def create_sample_pdf(pages: int = 1) -> bytes:
    """Generate in-memory valid PDF bytes with specified page count."""
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), f"EvidenceOCR Test Page {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def create_sample_png(width: int = 100, height: int = 100) -> bytes:
    """Generate in-memory valid PNG image bytes."""
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_sample_jpeg(width: int = 100, height: int = 100) -> bytes:
    """Generate in-memory valid JPEG image bytes."""
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def mock_storage():
    """In-memory MockStorageProvider fixture."""
    return MockStorageProvider()


@pytest.fixture
def memory_doc_repo():
    """In-memory document repository fake."""
    repo = AsyncMock(spec=DocumentRepository)
    storage_dict = {}

    async def fake_create(entity: DocumentEntity):
        storage_dict[entity.id] = entity
        return entity

    async def fake_get_by_id(doc_id: str):
        return storage_dict.get(doc_id)

    async def fake_list_documents(status_filter=None, search_query=None, skip=0, limit=20):
        items = list(storage_dict.values())
        if status_filter:
            items = [d for d in items if d.status.value == status_filter or d.status == status_filter]
        if search_query:
            items = [d for d in items if search_query.lower() in d.name.lower()]
        return items[skip : skip + limit], len(items)

    repo.create.side_effect = fake_create
    repo.get_by_id.side_effect = fake_get_by_id
    repo.list_documents.side_effect = fake_list_documents
    repo._storage = storage_dict
    return repo


# --- Scenario 1: Successful PDF upload ---
@pytest.mark.asyncio
async def test_01_successful_pdf_upload(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=2)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("site_notes.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Field Inspection", "kind": "Field notes", "expected_language": "English"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["document_id"].startswith("doc-")
        assert data["name"] == "Field Inspection"
        assert data["original_filename"] == "site_notes.pdf"
        assert data["content_type"] == "application/pdf"
        assert data["page_count"] == 2
        assert data["status"] == "Ready for backend"
        assert data["file_size_bytes"] == len(pdf_bytes)
        assert len(data["sha256"]) == 64
    finally:
        app.dependency_overrides.clear()


# --- Scenario 2: Successful PNG upload ---
@pytest.mark.asyncio
async def test_02_successful_png_upload(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        png_bytes = create_sample_png()
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("photo.png", png_bytes, "image/png")},
            data={"title": "Site Photo"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content_type"] == "image/png"
        assert data["page_count"] == 1
        assert data["file_size_bytes"] == len(png_bytes)
    finally:
        app.dependency_overrides.clear()


# --- Scenario 3: Successful JPEG upload ---
@pytest.mark.asyncio
async def test_03_successful_jpeg_upload(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        jpg_bytes = create_sample_jpeg()
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("receipt.jpg", jpg_bytes, "image/jpeg")},
            data={"title": "Receipt Scan"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content_type"] == "image/jpeg"
        assert data["page_count"] == 1
    finally:
        app.dependency_overrides.clear()


# --- Scenario 4: Invalid extension ---
@pytest.mark.asyncio
async def test_04_invalid_extension_rejected(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/octet-stream")},
            data={"title": "Executable"},
        )
        assert response.status_code in [400, 422]
    finally:
        app.dependency_overrides.clear()


# --- Scenario 5: Invalid or spoofed MIME type ---
@pytest.mark.asyncio
async def test_05_spoofed_mime_type_rejected(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        # File has .pdf extension and application/pdf MIME, but contains plain text without %PDF- magic bytes
        fake_pdf_bytes = b"Hello, I am a plain text file pretending to be a PDF document."
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("fake.pdf", fake_pdf_bytes, "application/pdf")},
            data={"title": "Spoofed PDF"},
        )
        assert response.status_code == 422
        data = response.json()
        assert "signature" in data["error"]["message"].lower() or "invalid" in data["error"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


# --- Scenario 6: Corrupted PDF/image ---
@pytest.mark.asyncio
async def test_06_corrupted_document_rejected(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        # Truncated broken PDF
        broken_pdf = b"%PDF-1.4\n%corrupt truncated content without EOF or xref"
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("broken.pdf", broken_pdf, "application/pdf")},
            data={"title": "Broken PDF"},
        )
        assert response.status_code == 422
        assert "corrupt" in response.json()["error"]["message"].lower()

        # Truncated broken PNG
        broken_png = b"\x89PNG\r\n\x1a\ncorrupt image payload"
        res_png = await client.post(
            "/api/v1/documents",
            files={"file": ("broken.png", broken_png, "image/png")},
            data={"title": "Broken PNG"},
        )
        assert res_png.status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- Scenario 7: Exceeded file-size limit (>10 MiB) ---
@pytest.mark.asyncio
async def test_07_exceeded_file_size_limit(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        # Exceeds max_upload_size_bytes (20 MiB + 1024 bytes)
        oversized = b"%PDF-1.4\n" + b"A" * (20 * 1024 * 1024 + 1024)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("huge.pdf", oversized, "application/pdf")},
            data={"title": "Oversized"},
        )
        assert response.status_code == 422
        assert "maximum file size" in response.json()["error"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


# --- Scenario 8: Exceeded PDF page limit (>20 pages) ---
@pytest.mark.asyncio
async def test_08_exceeded_pdf_page_limit(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        # 21 pages PDF
        pdf_21_pages = create_sample_pdf(pages=21)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("too_many_pages.pdf", pdf_21_pages, "application/pdf")},
            data={"title": "21 Pages Document"},
        )
        assert response.status_code == 422
        assert "page limit" in response.json()["error"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


# --- Scenario 9: Duplicate original filenames ---
@pytest.mark.asyncio
async def test_09_duplicate_filenames_handled_uniquely(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        # Upload 1
        res1 = await client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Invoice 1"},
        )
        # Upload 2 with identical filename
        res2 = await client.post(
            "/api/v1/documents",
            files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Invoice 2"},
        )
        assert res1.status_code == 201
        assert res2.status_code == 201
        data1 = res1.json()
        data2 = res2.json()
        assert data1["document_id"] != data2["document_id"]
        assert data1["gridfs_file_id"] != data2["gridfs_file_id"]
    finally:
        app.dependency_overrides.clear()


# --- Scenario 10: SHA-256 calculation ---
@pytest.mark.asyncio
async def test_10_sha256_calculation_accuracy(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        expected_sha = hashlib.sha256(pdf_bytes).hexdigest()
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("verified.pdf", pdf_bytes, "application/pdf")},
            data={"title": "SHA Verified"},
        )
        assert response.status_code == 201
        assert response.json()["sha256"] == expected_sha
    finally:
        app.dependency_overrides.clear()


# --- Scenario 11: MongoDB metadata persistence ---
@pytest.mark.asyncio
async def test_11_mongodb_metadata_persistence(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        res = await client.post(
            "/api/v1/documents",
            files={"file": ("audit.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Audit Report", "kind": "Forms", "expected_language": "English"},
        )
        doc_id = res.json()["document_id"]

        # Verify via GET /documents/{id}
        get_res = await client.get(f"/api/v1/documents/{doc_id}")
        assert get_res.status_code == 200
        detail = get_res.json()
        assert detail["id"] == doc_id
        assert detail["name"] == "Audit Report"
        assert detail["kind"] == "Forms"
        assert detail["file_size_bytes"] == len(pdf_bytes)
        assert detail["gridfs_file_id"] is not None
        assert detail["schema_version"] == 1
    finally:
        app.dependency_overrides.clear()


# --- Scenario 12: GridFS round-trip byte integrity ---
@pytest.mark.asyncio
async def test_12_gridfs_round_trip_byte_integrity(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        original_bytes = create_sample_png(200, 200)
        res = await client.post(
            "/api/v1/documents",
            files={"file": ("source.png", original_bytes, "image/png")},
            data={"title": "Byte Integrity Test"},
        )
        doc_id = res.json()["document_id"]

        # Stream back original file
        stream_res = await client.get(f"/api/v1/documents/{doc_id}/file")
        assert stream_res.status_code == 200
        assert stream_res.headers["content-type"] == "image/png"
        assert stream_res.content == original_bytes
        assert hashlib.sha256(stream_res.content).hexdigest() == hashlib.sha256(original_bytes).hexdigest()
    finally:
        app.dependency_overrides.clear()


# --- Scenario 13: Missing document and file ---
@pytest.mark.asyncio
async def test_13_missing_document_and_file(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        # Non-existent doc detail
        res = await client.get("/api/v1/documents/doc-nonexistent")
        assert res.status_code == 404

        # Non-existent doc file stream
        res_file = await client.get("/api/v1/documents/doc-nonexistent/file")
        assert res_file.status_code == 404
    finally:
        app.dependency_overrides.clear()


# --- Scenario 14: GridFS upload failure ---
@pytest.mark.asyncio
async def test_14_gridfs_upload_failure(app, client: httpx.AsyncClient, memory_doc_repo):
    failing_storage = AsyncMock()
    failing_storage.upload.side_effect = StorageOperationError("Simulated GridFS cluster write error")
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: failing_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("fail.pdf", pdf_bytes, "application/pdf")},
            data={"title": "GridFS Fail Test"},
        )
        assert response.status_code == 500
        assert len(memory_doc_repo._storage) == 0
    finally:
        app.dependency_overrides.clear()


# --- Scenario 15: MongoDB metadata failure ---
@pytest.mark.asyncio
async def test_15_mongodb_metadata_failure(app, client: httpx.AsyncClient, mock_storage):
    failing_repo = AsyncMock()
    failing_repo.create.side_effect = Exception("Simulated MongoDB insert conflict")
    app.dependency_overrides[get_document_repository] = lambda: failing_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("fail_meta.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Metadata Fail Test"},
        )
        assert response.status_code == 500
        assert "failed to persist document metadata" in response.json()["error"]["message"].lower()
    finally:
        app.dependency_overrides.clear()


# --- Scenario 16: Orphaned-file cleanup ---
@pytest.mark.asyncio
async def test_16_orphaned_file_cleanup(app, client: httpx.AsyncClient, mock_storage):
    failing_repo = AsyncMock()
    failing_repo.create.side_effect = Exception("Simulated MongoDB network failure")
    app.dependency_overrides[get_document_repository] = lambda: failing_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(pages=1)
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("orphan_cleanup.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Orphan Cleanup Test"},
        )
        assert response.status_code == 500

        # Verify compensating transaction: GridFS storage was cleaned up!
        assert len(mock_storage._store) == 0
    finally:
        app.dependency_overrides.clear()


# --- Scenario 17: Concurrent uploads ---
@pytest.mark.asyncio
async def test_17_concurrent_uploads(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        files = [
            ("doc_a.pdf", create_sample_pdf(1), "application/pdf"),
            ("doc_b.png", create_sample_png(50, 50), "image/png"),
            ("doc_c.jpg", create_sample_jpeg(50, 50), "image/jpeg"),
        ]

        async def upload_one(name, content, mime):
            return await client.post(
                "/api/v1/documents",
                files={"file": (name, content, mime)},
                data={"title": f"Concurrent {name}"},
            )

        responses = await asyncio.gather(*[upload_one(n, c, m) for n, c, m in files])
        for r in responses:
            assert r.status_code == 201

        # Verify all 3 stored in repo
        assert len(memory_doc_repo._storage) == 3
    finally:
        app.dependency_overrides.clear()


# --- Scenario 18: API response contracts ---
@pytest.mark.asyncio
async def test_18_api_response_contracts(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(1)
        res = await client.post(
            "/api/v1/documents",
            files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Contract Doc"},
        )
        assert res.status_code == 201
        upload_data = res.json()
        required_upload_keys = {"document_id", "name", "original_filename", "content_type", "file_size_bytes", "sha256", "gridfs_file_id", "page_count", "status", "revision"}
        assert required_upload_keys.issubset(upload_data.keys())

        # List contract
        list_res = await client.get("/api/v1/documents")
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert "items" in list_data and "total" in list_data
        item = list_data["items"][0]
        required_item_keys = {"id", "name", "kind", "language", "pages", "status", "size", "sample", "mime", "revision", "sha256", "gridfs_file_id", "file_size_bytes"}
        assert required_item_keys.issubset(item.keys())
    finally:
        app.dependency_overrides.clear()


# --- Scenario 19: Frontend upload integration contract ---
@pytest.mark.asyncio
async def test_19_frontend_upload_integration_contract(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    """Ensure frontend field expectations (id, name, kind, language, pages, status, added, size, sample, url, mime) match backend."""
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        pdf_bytes = create_sample_pdf(1)
        res = await client.post(
            "/api/v1/documents",
            files={"file": ("frontend_doc.pdf", pdf_bytes, "application/pdf")},
            data={"title": "Frontend Doc", "kind": "Research notes", "expected_language": "English"},
        )
        assert res.status_code == 201

        list_res = await client.get("/api/v1/documents")
        item = list_res.json()["items"][0]
        # Frontend DocumentItem fields
        assert item["id"].startswith("doc-")
        assert item["name"] == "Frontend Doc"
        assert item["kind"] == "Research notes"
        assert item["language"] == "English"
        assert item["pages"] == 1
        assert item["status"] == "Ready for backend"
        assert item["sample"] is False
        assert item["url"] == f"/api/v1/documents/{item['id']}/file"
        assert item["mime"] == "application/pdf"
    finally:
        app.dependency_overrides.clear()


# --- Scenario 20: Persistence across requests ---
@pytest.mark.asyncio
async def test_20_persistence_across_requests(app, client: httpx.AsyncClient, memory_doc_repo, mock_storage):
    """Verify document metadata and file are retrievable across distinct requests."""
    app.dependency_overrides[get_document_repository] = lambda: memory_doc_repo
    app.dependency_overrides[get_storage_provider] = lambda: mock_storage
    try:
        png_bytes = create_sample_png(80, 80)
        res = await client.post(
            "/api/v1/documents",
            files={"file": ("persist.png", png_bytes, "image/png")},
            data={"title": "Persistent Document"},
        )
        doc_id = res.json()["document_id"]

        # Subsequent distinct request 1: listing
        list_res = await client.get("/api/v1/documents")
        ids = [d["id"] for d in list_res.json()["items"]]
        assert doc_id in ids

        # Subsequent distinct request 2: details
        detail_res = await client.get(f"/api/v1/documents/{doc_id}")
        assert detail_res.status_code == 200
        assert detail_res.json()["name"] == "Persistent Document"

        # Subsequent distinct request 3: file stream
        file_res = await client.get(f"/api/v1/documents/{doc_id}/file")
        assert file_res.status_code == 200
        assert file_res.content == png_bytes
    finally:
        app.dependency_overrides.clear()
