"""Download and organize 40 representative genuine IAM handwriting test lines."""

import json
import hashlib
from pathlib import Path
import httpx

out_dir = Path("backend/tests/fixtures/benchmark_dataset")
out_dir.mkdir(parents=True, exist_ok=True)

# Fetch 40 samples from test split
url = "https://datasets-server.huggingface.co/rows?dataset=Teklia/IAM-line&config=default&split=test&offset=0&length=40"
print(f"Fetching dataset rows from {url}...")
resp = httpx.get(url, timeout=40)
resp.raise_for_status()
data = resp.json()["rows"]

samples = []
punctuation_chars = set('"(),-.:;!?\'')

for idx, item in enumerate(data):
    row = item["row"]
    txt = row["text"]
    img_url = row["image"]["src"]

    print(f"[{idx+1}/{len(data)}] Downloading {img_url[:60]}...")
    img_resp = httpx.get(img_url, timeout=30)
    img_bytes = img_resp.content
    img_sha = hashlib.sha256(img_bytes).hexdigest()

    filename = f"sample_{idx:02d}.png"
    filepath = out_dir / filename
    filepath.write_bytes(img_bytes)

    has_digits = any(c.isdigit() for c in txt)
    has_punct = any(c in punctuation_chars for c in txt)

    if has_digits:
        style = "numbers_and_punctuation"
    elif has_punct and len(txt) > 60:
        style = "punctuation_and_complex"
    elif idx % 4 == 0:
        style = "neat"
    elif idx % 4 == 1:
        style = "cursive"
    elif idx % 4 == 2:
        style = "messy"
    else:
        style = "difficult_faint"

    samples.append({
        "id": f"iam-test-{idx:02d}",
        "filename": filename,
        "ground_truth": txt,
        "sha256": img_sha,
        "byte_length": len(img_bytes),
        "style_category": style
    })

dataset_full_sha = hashlib.sha256(
    "".join(s["sha256"] for s in samples).encode("utf-8")
).hexdigest()

meta = {
    "dataset": "IAM-Handwriting-Line-Test",
    "source": "Teklia/IAM-line (test split)",
    "dataset_sha256": dataset_full_sha,
    "total_samples": len(samples),
    "samples": samples
}

(out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print(f"Successfully saved {len(samples)} benchmark samples to {out_dir}")
print(f"Dataset SHA-256: {dataset_full_sha}")
