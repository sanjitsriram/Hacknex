import asyncio
import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv('backend/.env')
sys.path.insert(0, 'backend/src')
from evidence_ocr.providers.paddleocr_vl import PaddleOCRVLCloudProvider

async def main():
    token = os.environ.get('PADDLEOCR_ACCESS_TOKEN', '')
    provider = PaddleOCRVLCloudProvider(access_token=token)
    img_path = Path('backend/tests/fixtures/sample_prescription.jpg')
    img_bytes = img_path.read_bytes()
    print(f'Parsing prescription image ({len(img_bytes)} bytes) with PaddleOCR-VL-1.6...')
    res = await provider.parse_document(img_bytes, 'image/jpeg')
    
    # Save first so file is always written
    out_file = Path('scripts/prescription_vl_result.json')
    out_file.write_text(res.model_dump_json(indent=2), encoding='utf-8')
    print(f'SUCCESS! Saved complete result to {out_file}')

    print('Execution time ms:', res.execution_time_ms)
    print('Total blocks:', res.total_blocks)
    print('Pages:', len(res.pages))
    print('Markdown length:', len(res.markdown_text))
    print('Provider metadata:', json.dumps(res.metadata.model_dump(), indent=2))
    for page in res.pages:
        print(f'Page {page.page_index} blocks: {len(page.blocks)}')
        for b in page.blocks:
            safe_content = b.content.replace('\n', ' ')[:70].encode('ascii', errors='backslashreplace').decode('ascii')
            print(f'  [{b.reading_order:02d}] {b.block_type:<16} (conf={b.confidence}): {safe_content}')

if __name__ == '__main__':
    asyncio.run(main())
