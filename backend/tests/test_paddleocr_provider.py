"""Unit and contract tests for PaddleOCRCloudProvider with PP-OCRv6."""

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest

from evidence_ocr.core.errors import InvalidInputError, ServiceUnavailableError
from evidence_ocr.providers.paddleocr import PaddleOCRCloudProvider


def _create_sample_png() -> bytes:
    """Generate minimal valid PNG image bytes (1000x1000)."""
    img = Image.new("RGB", (1000, 1000), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def paddle_provider():
    """Create test instance of PaddleOCRCloudProvider with dummy token."""
    return PaddleOCRCloudProvider(
        access_token="test-token-123",
        model="PP-OCRv6",
        base_url="https://paddleocr.test",
        request_timeout=5.0,
        poll_timeout=10.0,
    )


def test_paddleocr_provider_metadata(paddle_provider):
    """Verify provider metadata satisfies Invariant 3 (reproducible cloud versioning)."""
    meta = paddle_provider.get_metadata()
    assert meta.provider_name == "paddleocr-cloud"
    assert meta.model_identifier == "PP-OCRv6"
    assert meta.model_version == "PP-OCRv6"
    assert meta.parameters["base_url"] == "https://paddleocr.test"
    assert meta.parameters["request_timeout"] == 5.0
    assert meta.parameters["poll_timeout"] == 10.0


@pytest.mark.asyncio
async def test_rejects_empty_document(paddle_provider):
    """Verify empty document bytes are rejected immediately."""
    with pytest.raises(InvalidInputError, match="empty document bytes"):
        await paddle_provider.recognize_document(b"")


@pytest.mark.asyncio
async def test_rejects_missing_access_token():
    """Verify provider fails when access token is not configured."""
    provider = PaddleOCRCloudProvider(access_token="", model="PP-OCRv6")
    with pytest.raises(ServiceUnavailableError, match="credentials not configured"):
        await provider.recognize_document(_create_sample_png())


def test_normalize_polygon_bounds(paddle_provider):
    """Verify pixel polygon converts accurately to normalized percentage bounding box."""
    # 1000x1000 image, rectangle from x: 100..400, y: 200..300
    poly = [[100, 200], [400, 200], [400, 300], [100, 300]]
    bbox = paddle_provider._normalize_polygon(poly, 1000, 1000)

    assert bbox["x"] == 10.0
    assert bbox["y"] == 20.0
    assert bbox["w"] == 30.0
    assert bbox["h"] == 10.0
    assert bbox["x"] + bbox["w"] <= 100.0
    assert bbox["y"] + bbox["h"] <= 100.0


@pytest.mark.asyncio
async def test_recognize_document_success(paddle_provider):
    """Verify end-to-end cloud OCR simulation with mocked HTTP endpoints."""
    sample_png = _create_sample_png()

    # Mock responses
    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {
        "code": 0,
        "msg": "success",
        "data": {"jobId": "cloud-job-999"},
    }

    poll_response = MagicMock()
    poll_response.status_code = 200
    poll_response.json.return_value = {
        "code": 0,
        "data": {
            "state": "done",
            "resultUrl": {"jsonUrl": "https://paddleocr.test/artifacts/result.jsonl"},
        },
    }

    jsonl_text = json.dumps({
        "result": {
            "ocrResults": [
                {
                    "prunedResult": {
                        "rec_texts": ["A MOVE to stop, Mr. Gaitskell", "nomination of candidates"],
                        "rec_scores": [0.9632, 0.2500],
                        "dt_polys": [
                            [[100, 50], [900, 50], [900, 150], [100, 150]],
                            [[100, 200], [800, 200], [800, 300], [100, 300]],
                        ],
                    }
                }
            ]
        }
    })

    jsonl_response = MagicMock()
    jsonl_response.status_code = 200
    jsonl_response.text = jsonl_text
    jsonl_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = submit_response
    mock_client.get.side_effect = [poll_response, jsonl_response]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await paddle_provider.recognize_document(
            document_bytes=sample_png,
            mime_type="image/png",
            filename="sample.png",
        )

        assert result is not None
        assert "A MOVE to stop, Mr. Gaitskell" in result.raw_text
        assert len(result.detected_regions) == 2

        # Region 1: High confidence
        r1 = result.detected_regions[0]
        assert r1.text == "A MOVE to stop, Mr. Gaitskell"
        assert r1.confidence == 0.9632
        assert r1.is_illegible is False
        assert r1.bounding_box["x"] == 10.0
        assert r1.bounding_box["y"] == 5.0
        assert r1.bounding_box["w"] == 80.0
        assert r1.bounding_box["h"] == 10.0

        # Region 2: Low confidence (<0.30) marked illegible (Invariant 2)
        r2 = result.detected_regions[1]
        assert r2.text == "nomination of candidates"
        assert r2.confidence == 0.25
        assert r2.is_illegible is True


@pytest.mark.asyncio
async def test_handles_auth_failure(paddle_provider):
    """Verify HTTP 401 returns clear authentication error."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.post.return_value = resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ServiceUnavailableError, match="Invalid or unauthorized"):
            await paddle_provider.recognize_document(_create_sample_png())


@pytest.mark.asyncio
async def test_handles_rate_limit(paddle_provider):
    """Verify HTTP 429 returns quota / rate limit error."""
    resp = MagicMock()
    resp.status_code = 429
    resp.text = "Too Many Requests"

    mock_client = AsyncMock()
    mock_client.post.return_value = resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ServiceUnavailableError, match="rate limit"):
            await paddle_provider.recognize_document(_create_sample_png())


@pytest.mark.asyncio
async def test_handles_cloud_job_failure(paddle_provider):
    """Verify cloud execution failure ('state': 'failed') raises ServiceUnavailableError."""
    submit_response = MagicMock()
    submit_response.status_code = 200
    submit_response.json.return_value = {
        "code": 0,
        "msg": "success",
        "data": {"jobId": "failing-job"},
    }

    poll_response = MagicMock()
    poll_response.status_code = 200
    poll_response.json.return_value = {
        "code": 0,
        "data": {
            "state": "failed",
            "errorMsg": "Model crashed during inference",
        },
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = submit_response
    mock_client.get.return_value = poll_response

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ServiceUnavailableError, match="Model crashed during inference"):
            await paddle_provider.recognize_document(_create_sample_png())
