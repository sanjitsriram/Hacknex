import asyncio
import json
import os
import sys
import time
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Load environment
env_path = Path("backend/.env")
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

token = os.environ.get("PADDLEOCR_ACCESS_TOKEN", "").strip()
if not token:
    print(json.dumps({"error": "PADDLEOCR_ACCESS_TOKEN not set"}))
    sys.exit(1)

test_file = Path("backend/tests/fixtures/benchmark_dataset/sample_00.png")
if not test_file.exists():
    print(json.dumps({"error": f"Test file not found: {test_file}"}))
    sys.exit(1)

base_url = os.environ.get("PADDLEOCR_BASE_URL", "https://paddleocr.aistudio-app.com").rstrip("/")
model_name = "PaddleOCR-VL-1.6"

async def main():
    file_bytes = test_file.read_bytes()
    headers = {"Authorization": f"Bearer {token}"}
    optional_payload = {
        "useLayoutDetection": True,
        "prettifyMarkdown": True,
        "temperature": 0.0,
    }

    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Submit job
        submit_url = f"{base_url}/api/v2/ocr/jobs"
        files = {
            "file": (test_file.name, file_bytes, "image/png"),
        }
        data = {
            "model": model_name,
            "optionalPayload": json.dumps(optional_payload),
        }
        print(f"Submitting {test_file.name} to {submit_url} with model {model_name}...")
        try:
            submit_resp = await client.post(submit_url, headers=headers, data=data, files=files)
        except Exception as e:
            print(f"Submission failed network error: {e}")
            return

        print(f"HTTP Status: {submit_resp.status_code}")
        print(f"Submit Response: {submit_resp.text}")

        if submit_resp.status_code != 200:
            print(f"API rejection (status {submit_resp.status_code})")
            return

        resp_json = submit_resp.json()
        job_id = resp_json.get("data", {}).get("jobId")
        if not job_id:
            print(f"No jobId returned: {resp_json}")
            return

        print(f"Cloud Job ID: {job_id}")

        # 2. Poll for completion
        poll_url = f"{submit_url}/{job_id}"
        deadline = time.monotonic() + 300.0
        poll_interval = 2.0
        jsonl_url = None

        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                poll_resp = await client.get(poll_url, headers=headers)
                if poll_resp.status_code != 200:
                    print(f"Poll status: {poll_resp.status_code} - {poll_resp.text}")
                    continue

                poll_data = poll_resp.json().get("data", {})
                state = poll_data.get("state")
                print(f"Poll state: {state}")

                if state == "done":
                    jsonl_url = poll_data.get("resultUrl", {}).get("jsonUrl")
                    print(f"Result URL: {jsonl_url}")
                    break
                elif state == "failed":
                    print(f"Job failed: {poll_data.get('errorMsg')}")
                    return
                elif state in ("pending", "running"):
                    poll_interval = min(poll_interval * 1.2, 5.0)
                    continue
                else:
                    print(f"Unknown state: {state}")
            except Exception as e:
                print(f"Polling exception: {e}")

        if not jsonl_url:
            print("Timed out waiting for result.")
            return

        # 3. Download JSONL
        jsonl_resp = await client.get(jsonl_url)
        latency = round((time.perf_counter() - t0) * 1000.0, 2)
        print(f"Total Latency: {latency} ms")
        print("JSONL content length:", len(jsonl_resp.text))

        # Save to inspection file
        out_path = Path("scratch_vl_smoke_result.jsonl")
        out_path.write_text(jsonl_resp.text, encoding="utf-8")
        print(f"Saved full result artifact to {out_path}")

        # Parse and display structure
        for line in jsonl_resp.text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            res = item.get("result", {})
            print("Keys in result:", list(res.keys()))
            layout_res = res.get("layoutParsingResults", [])
            print(f"Number of layoutParsingResults pages: {len(layout_res)}")
            if layout_res:
                p0 = layout_res[0]
                print("Page 0 keys:", list(p0.keys()))
                md = p0.get("markdown", {})
                print("Markdown text sample:", repr(md.get("text", "")[:300]))
                pruned = p0.get("prunedResult", {})
                print("prunedResult keys:", list(pruned.keys()) if isinstance(pruned, dict) else type(pruned))
                if isinstance(pruned, dict):
                    res_list = pruned.get("parsing_res_list", [])
                    print(f"Number of blocks in parsing_res_list: {len(res_list)}")
                    for b_idx, block in enumerate(res_list[:5]):
                        print(f"  Block {b_idx}: id={block.get('block_id')}, label={block.get('block_label')}, order={block.get('block_order')}, bbox={block.get('block_bbox')}, content={repr(block.get('block_content', '')[:100])}")

if __name__ == "__main__":
    asyncio.run(main())
