"""TrOCR handwriting recognition provider implementing BaseOCRProvider."""

import asyncio
import io
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple
from PIL import Image
import torch
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

from evidence_ocr.core.errors import InvalidInputError, ServiceUnavailableError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.providers.ocr import BaseOCRProvider, OCRResult, OCRWord, ProviderMetadata

logger = get_logger("evidence_ocr.providers.trocr")

# Model and processor process-level singleton cache
_MODEL_CACHE: Dict[str, Tuple[TrOCRProcessor, VisionEncoderDecoderModel]] = {}
# Bounded threadpool to prevent CPU saturation across concurrent requests
_THREAD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trocr_worker")


def get_trocr_artifacts(
    model_name: str = "microsoft/trocr-base-handwritten",
    local_files_only: bool = True,
) -> Tuple[TrOCRProcessor, VisionEncoderDecoderModel]:
    """Retrieve or initialize cached TrOCR processor and model."""
    global _MODEL_CACHE
    if model_name not in _MODEL_CACHE:
        logger.info("Initializing TrOCR artifacts for %s (local_files_only=%s)...", model_name, local_files_only)
        try:
            processor = TrOCRProcessor.from_pretrained(model_name, local_files_only=local_files_only)
            model = VisionEncoderDecoderModel.from_pretrained(model_name, local_files_only=local_files_only)
            model.eval()
            _MODEL_CACHE[model_name] = (processor, model)
            logger.info("TrOCR model %s loaded successfully.", model_name)
        except Exception as exc:
            logger.exception("Failed to load TrOCR model %s: %s", model_name, exc)
            raise ServiceUnavailableError(f"TrOCR model initialization failed: {exc}") from exc
    return _MODEL_CACHE[model_name]


def _sync_inference(
    processor: TrOCRProcessor,
    model: VisionEncoderDecoderModel,
    image: Image.Image,
    max_new_tokens: int = 128,
) -> Tuple[str, float]:
    """Synchronous CPU inference executed inside bounded threadpool.
    
    Extracts decoder output softmax log-probabilities to compute genuine mathematical confidence.
    """
    with torch.inference_mode():
        pixel_values = processor(image, return_tensors="pt").pixel_values
        outputs = model.generate(
            pixel_values,
            max_new_tokens=max_new_tokens,
            return_dict_in_generate=True,
            output_scores=True,
        )
        tokens = outputs.sequences[0]
        step_scores = outputs.scores  # Tuple of (batch_size, vocab_size) logits
        
        probs = []
        for step_idx, step_logits in enumerate(step_scores):
            step_prob = torch.softmax(step_logits, dim=-1)
            # Token index 0 is decoder start token; token generated at step_idx is tokens[step_idx + 1]
            if step_idx + 1 < len(tokens):
                gen_token_id = tokens[step_idx + 1].item()
                probs.append(step_prob[0, gen_token_id].item())

        confidence = float(torch.tensor(probs).mean().item()) if probs else 0.0
        text = processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0].strip()
        return text, confidence


class TrOCRProvider(BaseOCRProvider):
    """Local TrOCR handwriting recognition engine implementing BaseOCRProvider."""

    def __init__(
        self,
        model_name: str = "microsoft/trocr-base-handwritten",
        version_tag: str = "base-handwritten-v1.0",
        max_new_tokens: int = 128,
        timeout_seconds: float = 30.0,
        local_files_only: bool = True,
    ) -> None:
        self.model_name = model_name
        self.version_tag = version_tag
        self.max_new_tokens = max_new_tokens
        self.timeout_seconds = timeout_seconds
        self.local_files_only = local_files_only

    def get_metadata(self) -> ProviderMetadata:
        """Return provider versioning metadata for reproducibility (Invariant 3)."""
        return ProviderMetadata(
            provider_name="trocr",
            model_identifier=self.model_name,
            model_version=self.version_tag,
            parameters={
                "device": "cpu",
                "max_new_tokens": self.max_new_tokens,
                "local_files_only": self.local_files_only,
                "torch_version": torch.__version__,
            },
        )

    async def recognize_page(
        self, image_bytes: bytes, language_hint: Optional[str] = None
    ) -> OCRResult:
        """Recognize handwritten line or crop image bytes asynchronously."""
        if not image_bytes or len(image_bytes) == 0:
            raise InvalidInputError("Cannot perform OCR on empty image bytes.")

        t0 = time.perf_counter()

        # Validate image format via PIL
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            logger.warning("Invalid image bytes provided to TrOCRProvider: %s", exc)
            raise InvalidInputError(f"Corrupted or unsupported image bytes: {exc}") from exc

        # Retrieve cached model and processor
        processor, model = get_trocr_artifacts(self.model_name, self.local_files_only)

        loop = asyncio.get_running_loop()
        try:
            # Execute in bounded threadpool to prevent blocking the FastAPI event loop
            text, confidence = await asyncio.wait_for(
                loop.run_in_executor(
                    _THREAD_POOL,
                    _sync_inference,
                    processor,
                    model,
                    image,
                    self.max_new_tokens,
                ),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.error("TrOCR inference timed out after %s seconds", self.timeout_seconds)
            raise ServiceUnavailableError(f"TrOCR inference timed out after {self.timeout_seconds}s") from exc
        except Exception as exc:
            logger.exception("TrOCR inference execution failed: %s", exc)
            raise ServiceUnavailableError(f"TrOCR inference execution failed: {exc}") from exc

        t1 = time.perf_counter()
        execution_time_ms = round((t1 - t0) * 1000.0, 2)

        # Word tokens with normalized relative positions
        words = []
        raw_words = text.split()
        if raw_words:
            word_w = 100.0 / len(raw_words)
            for idx, word_text in enumerate(raw_words):
                words.append(
                    OCRWord(
                        text=word_text,
                        confidence=confidence,
                        bounding_box={
                            "x": round(idx * word_w, 2),
                            "y": 0.0,
                            "w": round(word_w, 2),
                            "h": 100.0,
                        },
                    )
                )

        return OCRResult(
            raw_text=text,
            words=words,
            metadata=self.get_metadata(),
            execution_time_ms=execution_time_ms,
        )
