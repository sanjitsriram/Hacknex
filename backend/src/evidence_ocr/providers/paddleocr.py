"""PaddleOCR Cloud Provider for document text detection and recognition using PP-OCRv6."""

import asyncio
import hashlib
import io
import json
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from PIL import Image
import pypdfium2 as pdfium

from evidence_ocr.core.errors import (
    InvalidInputError,
    ServiceUnavailableError,
)
from evidence_ocr.core.logging import get_logger
from evidence_ocr.providers.ocr import (
    BaseOCRProvider,
    DetectedRegion,
    OCRResult,
    OCRWord,
    ProviderMetadata,
)

logger = get_logger("evidence_ocr.providers.paddleocr")


class PaddleOCRCloudProvider(BaseOCRProvider):
    """Official PaddleOCR Cloud API provider using PP-OCRv6."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        model: str = "PP-OCRv6",
        base_url: str = "https://paddleocr.aistudio-app.com",
        request_timeout: float = 60.0,
        poll_timeout: float = 300.0,
        max_concurrent_jobs: int = 2,
    ) -> None:
        self.access_token = access_token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.poll_timeout = poll_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)

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
            },
        )

    def _get_page_dimensions(self, document_bytes: bytes, mime_type: str) -> List[Tuple[int, int]]:
        """Determine exact pixel dimensions (W, H) for each page for accurate coordinate normalization."""
        clean_mime = (mime_type or "").lower().strip()
        dims: List[Tuple[int, int]] = []

        if "pdf" in clean_mime:
            try:
                pdf = pdfium.PdfDocument(document_bytes)
                for page_idx in range(len(pdf)):
                    page = pdf[page_idx]
                    # Render bitmap scale 2.77 (~200 DPI standard) to match vision rendering
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

    def _normalize_polygon(
        self,
        poly: List[List[float]],
        page_width: int,
        page_height: int,
    ) -> Dict[str, float]:
        """Normalize pixel polygon to percentage bounding box [0.0, 100.0] (Invariant 1)."""
        if not poly or len(poly) < 3:
            return {"x": 5.0, "y": 5.0, "w": 90.0, "h": 10.0}

        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]

        min_x = max(0.0, min(xs))
        max_x = min(float(page_width), max(xs))
        min_y = max(0.0, min(ys))
        max_y = min(float(page_height), max(ys))

        # Clamp and transform to percentage space
        w_px = max(1.0, max_x - min_x)
        h_px = max(1.0, max_y - min_y)

        x_pct = round((min_x / float(page_width)) * 100.0, 2)
        y_pct = round((min_y / float(page_height)) * 100.0, 2)
        w_pct = round((w_px / float(page_width)) * 100.0, 2)
        h_pct = round((h_px / float(page_height)) * 100.0, 2)

        # Ensure bounds compliance [0.0, 100.0]
        if x_pct + w_pct > 100.0:
            w_pct = max(0.1, round(100.0 - x_pct, 2))
        if y_pct + h_pct > 100.0:
            h_pct = max(0.1, round(100.0 - y_pct, 2))

        return {"x": x_pct, "y": y_pct, "w": w_pct, "h": h_pct}

    async def recognize_page(
        self, image_bytes: bytes, language_hint: Optional[str] = None
    ) -> OCRResult:
        """Execute OCR recognition on a single image byte stream."""
        return await self.recognize_document(
            document_bytes=image_bytes,
            mime_type="image/png",
            filename="page.png",
            language_hint=language_hint,
        )

    async def recognize_document(
        self,
        document_bytes: bytes,
        mime_type: str = "application/pdf",
        filename: Optional[str] = None,
        language_hint: Optional[str] = None,
    ) -> OCRResult:
        """Execute cloud document-level text detection and recognition on PP-OCRv6."""
        if not document_bytes or len(document_bytes) == 0:
            raise InvalidInputError("Cannot perform cloud OCR on empty document bytes.")

        if not self.access_token or not self.access_token.strip():
            logger.error("PaddleOCR Cloud API requested but PADDLEOCR_ACCESS_TOKEN is missing.")
            raise ServiceUnavailableError(
                "PaddleOCR Cloud API credentials not configured. Please supply PADDLEOCR_ACCESS_TOKEN in backend/.env"
            )

        t0 = time.perf_counter()
        doc_sha256 = hashlib.sha256(document_bytes).hexdigest()
        safe_filename = filename or ("document.pdf" if "pdf" in (mime_type or "").lower() else "document.png")

        # Resolve page dimensions for coordinate normalization
        page_dims = self._get_page_dimensions(document_bytes, mime_type)

        headers = {
            "Authorization": f"bearer {self.access_token.strip()}",
        }
        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useTextlineOrientation": False,
        }

        job_endpoint = f"{self.base_url}/api/v2/ocr/jobs"

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                # 1. Job Submission with Retry on Queue Congestion (Code 10010)
                resp = None
                max_submit_retries = 3
                for submit_attempt in range(1, max_submit_retries + 1):
                    try:
                        files = {
                            "file": (safe_filename, document_bytes, mime_type or "application/octet-stream"),
                        }
                        data = {
                            "model": self.model,
                            "optionalPayload": json.dumps(optional_payload),
                        }
                        logger.info(
                            "Submitting document (SHA-256: %s...) to PaddleOCR Cloud (%s) [attempt %s/%s]...",
                            doc_sha256[:8],
                            self.model,
                            submit_attempt,
                            max_submit_retries,
                        )
                        resp = await client.post(job_endpoint, headers=headers, data=data, files=files)
                    except httpx.TimeoutException as exc:
                        logger.error("PaddleOCR job submission timed out: %s", exc)
                        if submit_attempt == max_submit_retries:
                            raise ServiceUnavailableError(f"PaddleOCR submission timed out after {self.request_timeout}s") from exc
                        await asyncio.sleep(2.0 * submit_attempt)
                        continue
                    except Exception as exc:
                        logger.exception("PaddleOCR job submission network error: %s", exc)
                        if submit_attempt == max_submit_retries:
                            raise ServiceUnavailableError(f"PaddleOCR network error: {exc}") from exc
                        await asyncio.sleep(2.0 * submit_attempt)
                        continue

                    if resp.status_code in (401, 403):
                        logger.error("PaddleOCR Cloud rejected credentials with status %s", resp.status_code)
                        raise ServiceUnavailableError("Invalid or unauthorized PaddleOCR access token.")

                    # Handle queue saturation (Code 10010: "任务提交队列已满，请稍后重试")
                    is_queue_full = False
                    if resp.status_code in (400, 503):
                        try:
                            err_body = resp.json()
                            if err_body.get("code") == 10010 or "队列已满" in (err_body.get("msg") or ""):
                                is_queue_full = True
                        except Exception:
                            pass

                    if is_queue_full:
                        if submit_attempt < max_submit_retries:
                            retry_delay = 2.0 * submit_attempt
                            logger.warning(
                                "PaddleOCR cloud queue is currently full (code 10010). Retrying in %.1fs (attempt %s/%s)...",
                                retry_delay,
                                submit_attempt,
                                max_submit_retries,
                            )
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            logger.error("PaddleOCR cloud queue capacity exceeded after %s attempts.", max_submit_retries)
                            raise ServiceUnavailableError(
                                "PaddleOCR cloud inference queue is currently at capacity on Baidu AI Studio. Please retry in a few moments."
                            )

                    if resp.status_code == 429:
                        logger.error("PaddleOCR Cloud API rate limit exceeded.")
                        raise ServiceUnavailableError("PaddleOCR Cloud quota exceeded or rate limit reached (HTTP 429).")

                    if resp.status_code != 200:
                        logger.error("PaddleOCR Cloud returned error HTTP %s: %s", resp.status_code, resp.text)
                        raise ServiceUnavailableError(f"PaddleOCR submission failed (HTTP {resp.status_code}): {resp.text}")

                    # Break if submission succeeded with code 0
                    try:
                        resp_check = resp.json()
                        if resp_check.get("code") == 10010 and submit_attempt < max_submit_retries:
                            await asyncio.sleep(2.0 * submit_attempt)
                            continue
                    except Exception:
                        pass
                    break

                if resp is None:
                    raise ServiceUnavailableError("PaddleOCR submission failed: no response received.")

                resp_data = resp.json()
                if resp_data.get("code") != 0 or not resp_data.get("data", {}).get("jobId"):
                    err_msg = resp_data.get("msg") or "Unknown provider rejection"
                    if resp_data.get("code") == 10010:
                        err_msg = "PaddleOCR cloud queue is currently at capacity. Please try again in a few moments."
                    logger.error("PaddleOCR job rejected: %s", err_msg)
                    raise ServiceUnavailableError(f"PaddleOCR Cloud API rejected job: {err_msg}")

                cloud_job_id = resp_data["data"]["jobId"]
                logger.info("PaddleOCR Cloud job accepted. Cloud Job ID: %s", cloud_job_id)

                # 2. Polling for Completion
                poll_url = f"{job_endpoint}/{cloud_job_id}"
                deadline = time.monotonic() + self.poll_timeout
                poll_interval = 1.5
                jsonl_url: Optional[str] = None

                while time.monotonic() < deadline:
                    await asyncio.sleep(poll_interval)
                    try:
                        poll_resp = await client.get(poll_url, headers=headers)
                        if poll_resp.status_code != 200:
                            logger.warning("PaddleOCR polling received status %s", poll_resp.status_code)
                            continue

                        status_data = poll_resp.json().get("data", {})
                        state = status_data.get("state")

                        if state == "done":
                            jsonl_url = status_data.get("resultUrl", {}).get("jsonUrl")
                            logger.info("PaddleOCR job %s completed. Result JSONL: %s", cloud_job_id, jsonl_url)
                            break
                        elif state == "failed":
                            fail_reason = status_data.get("errorMsg") or "Provider execution failed"
                            logger.error("PaddleOCR job %s failed on provider side: %s", cloud_job_id, fail_reason)
                            raise ServiceUnavailableError(f"PaddleOCR Cloud execution failed: {fail_reason}")
                        elif state in ("pending", "running"):
                            poll_interval = min(poll_interval * 1.25, 5.0)
                            continue
                        else:
                            logger.warning("Unrecognized PaddleOCR state: %s", state)
                    except (ServiceUnavailableError, InvalidInputError):
                        raise
                    except Exception as poll_exc:
                        logger.warning("PaddleOCR polling error: %s (retrying)", poll_exc)

                if not jsonl_url:
                    logger.error("PaddleOCR job %s timed out after %s seconds", cloud_job_id, self.poll_timeout)
                    raise ServiceUnavailableError(f"PaddleOCR job timed out after {self.poll_timeout} seconds")

                # 3. Retrieve Result JSONL
                try:
                    jsonl_resp = await client.get(jsonl_url)
                    jsonl_resp.raise_for_status()
                    jsonl_content = jsonl_resp.text
                except Exception as exc:
                    logger.exception("Failed to retrieve result JSONL from %s: %s", jsonl_url, exc)
                    raise ServiceUnavailableError(f"Failed to fetch PaddleOCR result artifact: {exc}") from exc

        # 4. Result Parsing & Coordinate Normalization
        detected_regions: List[DetectedRegion] = []
        all_words: List[OCRWord] = []
        full_text_lines: List[str] = []

        for line_raw in jsonl_content.strip().split("\n"):
            line_str = line_raw.strip()
            if not line_str:
                continue
            try:
                line_json = json.loads(line_str)
                result_obj = line_json.get("result", {})
                ocr_results = result_obj.get("ocrResults", [])

                for page_idx, page_item in enumerate(ocr_results):
                    page_w, page_h = page_dims[page_idx] if page_idx < len(page_dims) else (page_dims[0] if page_dims else (1000, 1000))
                    pruned = page_item.get("prunedResult", {})
                    rec_texts = pruned.get("rec_texts", [])
                    rec_scores = pruned.get("rec_scores", [])
                    dt_polys = pruned.get("dt_polys", [])

                    for idx, (text_val, score_val, poly_coords) in enumerate(zip(rec_texts, rec_scores, dt_polys)):
                        clean_text = str(text_val).strip()
                        if not clean_text:
                            continue

                        confidence_val = float(score_val)
                        is_illegible = confidence_val < 0.30

                        # Calculate normalized [0, 100] bounding box
                        bbox_dict = self._normalize_polygon(poly_coords, page_w, page_h)

                        # Create DetectedRegion preserving both normalized box and original polygon
                        detected_regions.append(
                            DetectedRegion(
                                text=clean_text,
                                confidence=round(confidence_val, 4),
                                bounding_box=bbox_dict,
                                polygon=poly_coords,
                                page_index=page_idx,
                                is_illegible=is_illegible,
                            )
                        )
                        full_text_lines.append(clean_text)

                        # Create token words
                        all_words.append(
                            OCRWord(
                                text=clean_text,
                                confidence=round(confidence_val, 4),
                                bounding_box=bbox_dict,
                            )
                        )
            except Exception as parse_exc:
                logger.warning("Error parsing JSONL output line: %s", parse_exc)

        t1 = time.perf_counter()
        execution_time_ms = round((t1 - t0) * 1000.0, 2)

        meta = ProviderMetadata(
            provider_name="paddleocr-cloud",
            model_identifier=self.model,
            model_version=self.model,
            parameters={
                "cloud_job_id": cloud_job_id,
                "input_sha256": doc_sha256,
                "detected_regions_count": len(detected_regions),
                "pages_detected": len(page_dims),
            },
        )

        return OCRResult(
            raw_text="\n".join(full_text_lines),
            words=all_words,
            detected_regions=detected_regions,
            metadata=meta,
            execution_time_ms=execution_time_ms,
        )
