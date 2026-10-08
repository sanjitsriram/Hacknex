"""Unit and contract tests for PaddleOCRVLCloudProvider."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from evidence_ocr.core.errors import InvalidInputError, ServiceUnavailableError
from evidence_ocr.providers.paddleocr_vl import PaddleOCRVLCloudProvider


@pytest.fixture
def paddle_vl_provider():
    return PaddleOCRVLCloudProvider(
        access_token="test_paddle_token_12345",
        model="PaddleOCR-VL-1.6",
        base_url="https://mock-paddle.api",
        request_timeout=5.0,
        poll_timeout=10.0,
        max_concurrent_jobs=1,
    )


def test_metadata_reproducibility(paddle_vl_provider):
    """Verify provider metadata records explicit model versions (Invariant 3)."""
    meta = paddle_vl_provider.get_metadata()
    assert meta.provider_name == "paddleocr-cloud"
    assert meta.model_identifier == "PaddleOCR-VL-1.6"
    assert meta.model_version == "PaddleOCR-VL-1.6"
    assert meta.parameters["temperature"] == 0.0


def test_bounding_box_normalization(paddle_vl_provider):
    """Verify raw pixel coordinates [min_x, min_y, max_x, max_y] normalize to [0.0, 100.0]% (Invariant 1)."""
    bbox = paddle_vl_provider._normalize_box([100, 200, 500, 600], page_width=1000, page_height=1000)
    assert bbox.x == 10.0
    assert bbox.y == 20.0
    assert bbox.w == 40.0
    assert bbox.h == 40.0


@pytest.mark.asyncio
async def test_empty_document_rejection(paddle_vl_provider):
    """Verify empty document bytes raises InvalidInputError."""
    with pytest.raises(InvalidInputError, match="empty document bytes"):
        await paddle_vl_provider.parse_document(b"")


@pytest.mark.asyncio
async def test_missing_token_rejection():
    """Verify missing token raises ServiceUnavailableError."""
    provider = PaddleOCRVLCloudProvider(access_token=None)
    with pytest.raises(ServiceUnavailableError, match="credentials not configured"):
        await provider.parse_document(b"non-empty-bytes")


@pytest.mark.asyncio
async def test_successful_document_parsing(paddle_vl_provider):
    """Verify full document parsing lifecycle: submit -> poll -> fetch JSONL -> structured result."""
    submit_resp = MagicMock()
    submit_resp.status_code = 200
    submit_resp.json.return_value = {
        "code": 0,
        "msg": "Success",
        "data": {"jobId": "mock-vl-job-777"},
    }

    poll_resp = MagicMock()
    poll_resp.status_code = 200
    poll_resp.json.return_value = {
        "code": 0,
        "data": {
            "state": "done",
            "resultUrl": {"jsonUrl": "https://mock-storage.api/vl_result.jsonl"},
        },
    }

    sample_jsonl = json.dumps({
        "result": {
            "layoutParsingResults": [
                {
                    "prunedResult": {
                        "width": 1000,
                        "height": 1414,
                        "layout_det_res": {
                            "boxes": [
                                {"order": 1, "score": 0.95},
                                {"order": 2, "score": 0.91},
                            ]
                        },
                        "parsing_res_list": [
                            {
                                "block_id": 0,
                                "block_label": "paragraph_title",
                                "block_order": 1,
                                "block_bbox": [50, 50, 950, 150],
                                "block_content": "Site Inspection Report",
                            },
                            {
                                "block_id": 1,
                                "block_label": "table",
                                "block_order": 2,
                                "block_bbox": [50, 200, 950, 600],
                                "block_content": "| Item | Status |\n|---|---|\n| Wall | Sound |",
                            },
                        ],
                    },
                    "markdown": {
                        "text": "# Site Inspection Report\n\n| Item | Status |\n|---|---|\n| Wall | Sound |"
                    },
                }
            ]
        }
    })

    jsonl_resp = MagicMock()
    jsonl_resp.status_code = 200
    jsonl_resp.text = sample_jsonl
    jsonl_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post.return_value = submit_resp
    mock_client.get.side_effect = [poll_resp, jsonl_resp]

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await paddle_vl_provider.parse_document(
            document_bytes=b"fake-image-bytes",
            mime_type="image/png",
            filename="inspection.png",
        )

        assert result is not None
        assert "# Site Inspection Report" in result.markdown_text
        assert len(result.pages) == 1
        page0 = result.pages[0]
        assert page0.width == 1000
        assert page0.height == 1414
        assert len(page0.blocks) == 2
        assert page0.tables_count == 1

        b0 = page0.blocks[0]
        assert b0.block_type == "paragraph_title"
        assert b0.reading_order == 1
        assert b0.confidence == 0.95
        assert b0.bounding_box.x == 5.0
        assert b0.bounding_box.y == 3.54

        b1 = page0.blocks[1]
        assert b1.block_type == "table"
        assert b1.reading_order == 2
        assert b1.confidence == 0.91


@pytest.mark.asyncio
async def test_auth_failure_handling(paddle_vl_provider):
    """Verify HTTP 401 returns clear authorization error."""
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.post.return_value = resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        with pytest.raises(ServiceUnavailableError, match="unauthorized"):
            await paddle_vl_provider.parse_document(b"doc-bytes")


@pytest.mark.asyncio
async def test_quota_exceeded_handling(paddle_vl_provider):
    """Verify HTTP 429 returns rate limit error."""
    resp = MagicMock()
    resp.status_code = 429
    resp.text = "Rate Limit Exceeded"

    mock_client = AsyncMock()
    mock_client.post.return_value = resp

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        with pytest.raises(ServiceUnavailableError, match="quota exceeded"):
            await paddle_vl_provider.parse_document(b"doc-bytes")
