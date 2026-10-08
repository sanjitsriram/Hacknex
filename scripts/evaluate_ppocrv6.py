"""Reproducible evaluation framework for PP-OCRv6 Cloud OCR on IAM benchmark dataset.

Measures Character Error Rate (CER), Word Error Rate (WER), Exact-match rate,
and cloud network latency. Adheres strictly to Invariant 3 and Invariant 5.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
import jiwer
import numpy as np
from dotenv import load_dotenv

# Ensure backend package can be imported
sys.path.insert(0, str(Path("backend/src").resolve()))

from evidence_ocr.providers.paddleocr import PaddleOCRCloudProvider


async def run_evaluation(num_samples: int = 10, batch_pause: float = 0.5):
    # Load environment variables
    env_path = Path("backend/.env")
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

    token = os.environ.get("PADDLEOCR_ACCESS_TOKEN", "").strip()
    model = os.environ.get("PADDLEOCR_MODEL", "PP-OCRv6").strip()
    base_url = os.environ.get("PADDLEOCR_BASE_URL", "https://paddleocr.aistudio-app.com").strip()

    if not token:
        print("ERROR: PADDLEOCR_ACCESS_TOKEN not found in environment or backend/.env")
        sys.exit(1)

    dataset_dir = Path("backend/tests/fixtures/benchmark_dataset")
    meta_path = dataset_dir / "metadata.json"
    if not meta_path.exists():
        print(f"ERROR: Benchmark dataset metadata not found at {meta_path}")
        sys.exit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    all_samples = meta["samples"]
    samples = all_samples[:num_samples] if num_samples > 0 else all_samples

    print("================================================================")
    print(" EvidenceOCR - Phase 4 PP-OCRv6 Cloud OCR Performance Benchmark")
    print(f" Provider: paddleocr-cloud | Model: {model}")
    print(f" Endpoint: {base_url}")
    print(f" Dataset: {meta['dataset']} ({len(samples)} evaluated lines)")
    print(f" Dataset SHA-256: {meta['dataset_sha256']}")
    print("================================================================")

    provider = PaddleOCRCloudProvider(
        access_token=token,
        model=model,
        base_url=base_url,
        request_timeout=60.0,
        poll_timeout=120.0,
        max_concurrent_jobs=1,
    )

    results = []
    latencies = []
    all_ground_truths = []
    all_predictions = []
    exact_matches = 0
    total_chars = 0
    total_words = 0

    for i, s in enumerate(samples):
        img_path = dataset_dir / s["filename"]
        img_bytes = img_path.read_bytes()
        gt = s["ground_truth"].strip()

        t0 = time.perf_counter()
        try:
            ocr_result = await provider.recognize_document(
                document_bytes=img_bytes,
                mime_type="image/png",
                filename=s["filename"],
            )
            # Combine detected lines
            pred = " ".join([r.text for r in ocr_result.detected_regions]).strip()
        except Exception as exc:
            print(f"[{i+1:02d}/{len(samples)}] ERROR evaluating {s['filename']}: {exc}")
            pred = ""

        latency_sec = time.perf_counter() - t0
        latencies.append(latency_sec)

        all_ground_truths.append(gt)
        all_predictions.append(pred)

        sample_cer = jiwer.cer(gt, pred) if pred else 1.0
        sample_wer = jiwer.wer(gt, pred) if pred else 1.0
        is_exact = (gt == pred)
        if is_exact:
            exact_matches += 1

        total_chars += len(gt)
        total_words += len(gt.split())

        res = {
            "id": s["id"],
            "filename": s["filename"],
            "style_category": s["style_category"],
            "ground_truth": gt,
            "prediction": pred,
            "confidence": ocr_result.detected_regions[0].confidence if ocr_result.detected_regions else None,
            "latency_sec": round(latency_sec, 3),
            "cer": round(sample_cer, 4),
            "wer": round(sample_wer, 4),
            "exact_match": is_exact,
        }
        results.append(res)
        print(f"[{i+1:02d}/{len(samples)}] ({latency_sec:.2f}s | CER: {sample_cer:.2f}) GT: '{gt[:30]}...' -> PRED: '{pred[:30]}...'")

        if batch_pause > 0 and i < len(samples) - 1:
            await asyncio.sleep(batch_pause)

    overall_cer = jiwer.cer(all_ground_truths, all_predictions)
    overall_wer = jiwer.wer(all_ground_truths, all_predictions)
    exact_match_rate = (exact_matches / len(samples)) * 100.0

    lat_arr = np.array(latencies)
    latency_summary = {
        "mean_sec": round(float(np.mean(lat_arr)), 3),
        "median_p50_sec": round(float(np.median(lat_arr)), 3),
        "min_sec": round(float(np.min(lat_arr)), 3),
        "max_sec": round(float(np.max(lat_arr)), 3),
    }

    benchmark_summary = {
        "benchmark_id": "eval-ppocrv6-cloud-iam-v1",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_name": meta["dataset"],
        "dataset_sha256": meta["dataset_sha256"],
        "provider": "paddleocr-cloud",
        "model_identifier": model,
        "evaluated_samples": len(samples),
        "total_characters_evaluated": total_chars,
        "total_words_evaluated": total_words,
        "metrics": {
            "cer": round(float(overall_cer), 4),
            "wer": round(float(overall_wer), 4),
            "exact_match_rate_pct": round(exact_match_rate, 2),
            "exact_matches_count": exact_matches,
        },
        "latencies": latency_summary,
        "sample_evaluations": results,
    }

    out_json = dataset_dir / "benchmark_results_ppocrv6.json"
    out_json.write_text(json.dumps(benchmark_summary, indent=2), encoding="utf-8")

    print("\n================================================================")
    print(" BENCHMARK RESULTS SUMMARY:")
    print(f" Evaluated Samples: {len(samples)}")
    print(f" Character Error Rate (CER): {overall_cer * 100:.2f}% ({overall_cer:.4f})")
    print(f" Word Error Rate (WER):      {overall_wer * 100:.2f}% ({overall_wer:.4f})")
    print(f" Exact Match Rate:           {exact_match_rate:.1f}% ({exact_matches}/{len(samples)})")
    print(f" Median Latency (P50):       {latency_summary['median_p50_sec']} s")
    print(f" Results written to:         {out_json}")
    print("================================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate PP-OCRv6 Cloud OCR")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples to evaluate (default: 10)")
    parser.add_argument("--pause", type=float, default=0.5, help="Pause between API calls (seconds)")
    args = parser.parse_args()

    asyncio.run(run_evaluation(num_samples=args.samples, batch_pause=args.pause))
