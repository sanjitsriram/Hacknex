"""Tests for provider interfaces and mock implementations."""

import pytest
from evidence_ocr.providers.ocr import MockOCRProvider
from evidence_ocr.providers.storage import MockStorageProvider
from evidence_ocr.providers.vlm import MockVLMProvider, VLMRecoveryRequest


@pytest.mark.asyncio
async def test_ocr_provider_metadata_and_execution():
    """Verify OCR provider returns reproducible metadata and structured results."""
    provider = MockOCRProvider(model_version="mock-test-v1")
    meta = provider.get_metadata()
    assert meta.provider_name == "mock-ocr"
    assert meta.model_version == "mock-test-v1"
    assert meta.parameters["temperature"] == 0.0

    result = await provider.recognize_page(b"fake_image_bytes")
    assert result.raw_text != ""
    assert len(result.words) > 0
    assert result.words[0].confidence > 0.0
    assert result.metadata.model_version == "mock-test-v1"


@pytest.mark.asyncio
async def test_vlm_provider_recovery():
    """Verify VLM provider recovery interface."""
    vlm = MockVLMProvider(model_version="vlm-test-v1")
    req = VLMRecoveryRequest(
        crop_bytes=b"fake_crop",
        surrounding_context="The north wall measures ... metres.",
        competing_candidates=["4.8", "4.3"],
    )
    res = await vlm.inspect_crop(req)
    assert res.proposed_text == "4.8"
    assert res.confidence > 0.8
    assert res.reasoning != ""
    assert res.metadata.model_version == "vlm-test-v1"


@pytest.mark.asyncio
async def test_storage_provider_upload_and_download():
    """Verify object storage provider upload, download, and URL generation."""
    storage = MockStorageProvider()
    key = "documents/test-key.png"
    data = b"\x89PNG\r\n\x1a\nfake_image_data"

    uploaded_key = await storage.upload(key, data, "image/png")
    assert uploaded_key == key

    downloaded = await storage.download(key)
    assert downloaded == data

    url = await storage.generate_access_url(key)
    assert key in url
