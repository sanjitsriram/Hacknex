"""PaddleOCR-VL-1.6 Cloud Provider for document intelligence, layout parsing, and reading order."""

import asyncio
import hashlib
import io
import json
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from PIL import Image
import pypdfium2 as pdfium
from pydantic import BaseModel, Field

from evidence_ocr.core.errors import (
    InvalidInputError,
    ServiceUnavailableError,
)
from evidence_ocr.core.logging import get_logger
from evidence_ocr.models.parsing import LayoutBlock, ParsedPage
from evidence_ocr.models.region import BoundingBox
from evidence_ocr.providers.ocr import ProviderMetadata

logger = get_logger("evidence_ocr.providers.paddleocr_vl")


class ParsedDocumentResult(BaseModel):
    """Structured result returned by PaddleOCR-VL document intelligence."""

    markdown_text: str = Field(description="Consolidated Markdown text across pages")
    pages: List[ParsedPage] = Field(default_factory=list, description="Parsed pages with layout blocks")
    total_blocks: int = Field(default=0, ge=0, description="Total layout blocks extracted")
    metadata: ProviderMetadata = Field(description="Reproducible provider execution metadata")
    execution_time_ms: float = Field(ge=0.0, description="Total execution latency in milliseconds")


class PaddleOCRVLCloudProvider:
    """Official hosted PaddleOCR-VL cloud provider for document layout intelligence."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        model: str = "PaddleOCR-VL-1.6",
        base_url: str = "https://paddleocr.aistudio-app.com",
        request_timeout: float = 60.0,
        poll_timeout: float = 300.0,
        max_concurrent_jobs: int = 1,
    ) -> None:
        self.access_token = access_token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.poll_timeout = poll_timeout
        self._semaphore = asyncio.Semaphore(max(1, max_concurrent_jobs))

    def get_metadata(self) -> ProviderMetadata:
        """Return provider versioning metadata ensuring reproducibility (Invariant 3)."""
        return ProviderMetadata(
            provider_name="paddleocr-cloud",
            model_identifier=self.model,
            model_version=self.model,
            parameters={
                "base_url": self.base_url,
                "request_timeout": self.request_timeout,
                "poll_timeout": self.poll_timeout,
                "temperature": 0.0,
            },
        )

    def _get_page_dimensions(self, document_bytes: bytes, mime_type: str) -> List[Tuple[int, int]]:
        """Determine exact pixel dimensions (W, H) for each page as fallback."""
        clean_mime = (mime_type or "").lower().strip()
        dims: List[Tuple[int, int]] = []

        if "pdf" in clean_mime:
            try:
                pdf = pdfium.PdfDocument(document_bytes)
                for page_idx in range(len(pdf)):
                    page = pdf[page_idx]
                    width_px = int(page.get_width() * 2.77)
                    height_px = int(page.get_height() * 2.77)
                    dims.append((max(1, width_px), max(1, height_px)))
            except Exception as exc:
                logger.warning("Could not extract PDF page dimensions: %s", exc)
                dims.append((1000, 1414))
        else:
            try:
                img = Image.open(io.BytesIO(document_bytes))
                dims.append(img.size)
            except Exception as exc:
                logger.warning("Could not extract image dimensions: %s", exc)
                dims.append((1000, 1000))

        return dims

    def _normalize_box(
        self,
        raw_box: List[float],
        page_width: int,
        page_height: int,
    ) -> BoundingBox:
        """Normalize [min_x, min_y, max_x, max_y] to percentage BoundingBox in [0.0, 100.0] space."""
        if not raw_box or len(raw_box) < 4:
            return BoundingBox(x=5.0, y=5.0, w=90.0, h=10.0)

        min_x = max(0.0, float(raw_box[0]))
        min_y = max(0.0, float(raw_box[1]))
        max_x = min(float(page_width), float(raw_box[2]))
        max_y = min(float(page_height), float(raw_box[3]))

        w_px = max(1.0, max_x - min_x)
        h_px = max(1.0, max_y - min_y)

        x_pct = round((min_x / float(page_width)) * 100.0, 2)
        y_pct = round((min_y / float(page_height)) * 100.0, 2)
        w_pct = round((w_px / float(page_width)) * 100.0, 2)
        h_pct = round((h_px / float(page_height)) * 100.0, 2)

        if x_pct + w_pct > 100.0:
            w_pct = max(0.1, round(100.0 - x_pct, 2))
        if y_pct + h_pct > 100.0:
            h_pct = max(0.1, round(100.0 - y_pct, 2))

        return BoundingBox(x=x_pct, y=y_pct, w=w_pct, h=h_pct)

    async def parse_document(
        self,
        document_bytes: bytes,
        mime_type: str = "application/pdf",
        filename: Optional[str] = None,
    ) -> ParsedDocumentResult:
        """Submit document to hosted PaddleOCR-VL-1.6 and return structured parsing results."""
        if not document_bytes or len(document_bytes) == 0:
            raise InvalidInputError("Cannot perform document parsing on empty document bytes.")

        if not self.access_token or not self.access_token.strip():
            logger.error("PaddleOCR-VL Cloud API requested but PADDLEOCR_ACCESS_TOKEN is missing.")
            raise ServiceUnavailableError(
                "PaddleOCR Cloud API credentials not configured. Please supply PADDLEOCR_ACCESS_TOKEN in backend/.env"
            )

        t0 = time.perf_counter()
        doc_sha256 = hashlib.sha256(document_bytes).hexdigest()
        safe_filename = filename or ("document.pdf" if "pdf" in (mime_type or "").lower() else "document.png")

        fallback_page_dims = self._get_page_dimensions(document_bytes, mime_type)

        headers = {
            "Authorization": f"Bearer {self.access_token.strip()}",
        }
        optional_payload = {
            "useLayoutDetection": True,
            "prettifyMarkdown": True,
            "temperature": 0.0,
        }

        job_endpoint = f"{self.base_url}/api/v2/ocr/jobs"

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                # 1. Job Submission
                try:
                    files = {
                        "file": (safe_filename, document_bytes, mime_type or "application/octet-stream"),
                    }
                    data = {
                        "model": self.model,
                        "optionalPayload": json.dumps(optional_payload),
                    }
                    logger.info(
                        "Submitting document (SHA-256: %s...) to PaddleOCR-VL (%s)...",
                        doc_sha256[:8],
                        self.model,
                    )
                    resp = await client.post(job_endpoint, headers=headers, data=data, files=files)
                except httpx.TimeoutException as exc:
                    logger.error("PaddleOCR-VL job submission timed out: %s", exc)
                    raise ServiceUnavailableError(
                        f"PaddleOCR-VL submission timed out after {self.request_timeout}s"
                    ) from exc
                except Exception as exc:
                    logger.exception("PaddleOCR-VL job submission network error: %s", exc)
                    raise ServiceUnavailableError(f"PaddleOCR-VL network error: {exc}") from exc

                if resp.status_code in (401, 403):
                    logger.error("PaddleOCR-VL Cloud rejected credentials with status %s", resp.status_code)
                    raise ServiceUnavailableError("Invalid or unauthorized PaddleOCR access token.")
                elif resp.status_code == 429:
                    logger.error("PaddleOCR-VL Cloud API rate limit exceeded.")
                    raise ServiceUnavailableError("PaddleOCR Cloud quota exceeded or rate limit reached (HTTP 429).")
                elif resp.status_code != 200:
                    logger.error("PaddleOCR-VL Cloud returned HTTP %s: %s", resp.status_code, resp.text)
                    raise ServiceUnavailableError(f"PaddleOCR-VL submission failed (HTTP {resp.status_code}): {resp.text}")

                resp_data = resp.json()
                if resp_data.get("code") != 0 or not resp_data.get("data", {}).get("jobId"):
                    err_msg = resp_data.get("msg") or "Unknown provider rejection"
                    logger.error("PaddleOCR-VL job rejected: %s", err_msg)
                    raise ServiceUnavailableError(f"PaddleOCR Cloud API rejected job: {err_msg}")

                cloud_job_id = resp_data["data"]["jobId"]
                logger.info("PaddleOCR-VL Cloud job accepted. Cloud Job ID: %s", cloud_job_id)

                # 2. Polling for Completion
                poll_url = f"{job_endpoint}/{cloud_job_id}"
                deadline = time.monotonic() + self.poll_timeout
                poll_interval = 2.0
                jsonl_url: Optional[str] = None

                while time.monotonic() < deadline:
                    await asyncio.sleep(poll_interval)
                    try:
                        poll_resp = await client.get(poll_url, headers=headers)
                        if poll_resp.status_code != 200:
                            logger.warning("PaddleOCR-VL polling received status %s", poll_resp.status_code)
                            continue

                        status_data = poll_resp.json().get("data", {})
                        state = status_data.get("state")

                        if state == "done":
                            jsonl_url = status_data.get("resultUrl", {}).get("jsonUrl")
                            logger.info("PaddleOCR-VL job %s completed. Result JSONL: %s", cloud_job_id, jsonl_url)
                            break
                        elif state == "failed":
                            fail_reason = status_data.get("errorMsg") or "Provider execution failed"
                            logger.error("PaddleOCR-VL job %s failed on provider side: %s", cloud_job_id, fail_reason)
                            raise ServiceUnavailableError(f"PaddleOCR-VL Cloud execution failed: {fail_reason}")
                        elif state in ("pending", "running"):
                            poll_interval = min(poll_interval * 1.25, 5.0)
                            continue
                        else:
                            logger.warning("Unrecognized PaddleOCR-VL state: %s", state)
                    except (ServiceUnavailableError, InvalidInputError):
                        raise
                    except Exception as poll_exc:
                        logger.warning("PaddleOCR-VL polling error: %s (retrying)", poll_exc)

                if not jsonl_url:
                    logger.error("PaddleOCR-VL job %s timed out after %s seconds", cloud_job_id, self.poll_timeout)
                    raise ServiceUnavailableError(f"PaddleOCR-VL job timed out after {self.poll_timeout} seconds")

                # 3. Retrieve Result JSONL
                try:
                    jsonl_resp = await client.get(jsonl_url)
                    jsonl_resp.raise_for_status()
                    jsonl_content = jsonl_resp.text
                except Exception as exc:
                    logger.exception("Failed to retrieve result JSONL from %s: %s", jsonl_url, exc)
                    raise ServiceUnavailableError(f"Failed to fetch PaddleOCR-VL result artifact: {exc}") from exc

        # 4. Result Parsing, Coordinate Normalization & Reading Order Structuring
        parsed_pages: List[ParsedPage] = []
        consolidated_markdown: List[str] = []
        total_blocks_count = 0

        for line_raw in jsonl_content.strip().split("\n"):
            line_str = line_raw.strip()
            if not line_str:
                continue
            try:
                line_json = json.loads(line_str)
                result_obj = line_json.get("result", {})
                layout_results = result_obj.get("layoutParsingResults", [])

                for page_idx, page_item in enumerate(layout_results):
                    pruned = page_item.get("prunedResult", {})
                    md_obj = page_item.get("markdown", {})
                    page_md = md_obj.get("text", "")
                    consolidated_markdown.append(page_md)

                    # Extract page width & height directly from provider pruned result
                    page_w = pruned.get("width")
                    page_h = pruned.get("height")
                    if not page_w or not page_h or page_w <= 0 or page_h <= 0:
                        fallback = (
                            fallback_page_dims[page_idx]
                            if page_idx < len(fallback_page_dims)
                            else (fallback_page_dims[0] if fallback_page_dims else (1000, 1000))
                        )
                        page_w, page_h = fallback

                    # Build confidence lookup from layout_det_res.boxes
                    layout_det = pruned.get("layout_det_res", {})
                    det_boxes = layout_det.get("boxes", []) if isinstance(layout_det, dict) else []
                    score_by_order: Dict[int, float] = {}
                    for box in det_boxes:
                        order_key = box.get("order")
                        box_score = box.get("score")
                        if order_key is not None and box_score is not None:
                            score_by_order[order_key] = round(float(box_score), 4)

                    parsing_list = pruned.get("parsing_res_list", [])
                    blocks_on_page: List[LayoutBlock] = []
                    order_sequence: List[str] = []
                    tables_count = 0

                    for item_idx, block_dict in enumerate(parsing_list):
                        raw_id = block_dict.get("block_id")
                        if raw_id is not None:
                            b_id_str = f"blk-p{page_idx}-{raw_id}"
                        else:
                            b_id_str = f"blk-p{page_idx}-{item_idx:03d}"

                        b_label = block_dict.get("block_label", "text")
                        b_content = block_dict.get("block_content", "")
                        raw_order = block_dict.get("block_order")
                        b_order = int(raw_order) if raw_order is not None else (item_idx + 1)
                        raw_bbox = block_dict.get("block_bbox", [0, 0, page_w, page_h])
                        polygon_pts = block_dict.get("block_polygon_points")

                        if "table" in b_label.lower():
                            tables_count += 1

                        bbox = self._normalize_box(raw_bbox, page_w, page_h)
                        conf = score_by_order.get(b_order)

                        layout_block = LayoutBlock(
                            block_id=b_id_str,
                            page_index=page_idx,
                            block_type=b_label,
                            bounding_box=bbox,
                            polygon=polygon_pts,
                            raw_bbox=raw_bbox,
                            content=b_content,
                            reading_order=b_order,
                            confidence=conf,
                        )
                        blocks_on_page.append(layout_block)
                        order_sequence.append(b_id_str)
                        total_blocks_count += 1

                    # Sort blocks by reading order explicitly
                    blocks_on_page.sort(key=lambda b: b.reading_order)

                    parsed_pages.append(
                        ParsedPage(
                            page_index=page_idx,
                            width=page_w,
                            height=page_h,
                            markdown_text=page_md,
                            blocks=blocks_on_page,
                            reading_order_sequence=order_sequence,
                            tables_count=tables_count,
                        )
                    )
            except Exception as parse_exc:
                logger.warning("Error parsing layout parsing result line: %s", parse_exc)

        t1 = time.perf_counter()
        execution_time_ms = round((t1 - t0) * 1000.0, 2)

        meta = ProviderMetadata(
            provider_name="paddleocr-cloud",
            model_identifier=self.model,
            model_version=self.model,
            parameters={
                "cloud_job_id": cloud_job_id,
                "input_sha256": doc_sha256,
                "pages_parsed": len(parsed_pages),
                "total_blocks": total_blocks_count,
            },
        )

        return ParsedDocumentResult(
            markdown_text="\n\n".join(consolidated_markdown),
            pages=parsed_pages,
            total_blocks=total_blocks_count,
            metadata=meta,
            execution_time_ms=execution_time_ms,
        )
