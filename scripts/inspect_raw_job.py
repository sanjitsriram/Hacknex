import httpx
import os
import json
import asyncio
from dotenv import load_dotenv

load_dotenv('backend/.env')
token = os.environ.get('PADDLEOCR_ACCESS_TOKEN', '')

async def check():
    headers = {'Authorization': f'Bearer {token}'}
    async with httpx.AsyncClient() as client:
        r = await client.get('https://paddleocr.aistudio-app.com/api/v2/ocr/jobs/101768449048543232', headers=headers)
        data = r.json().get('data', {})
        json_url = data.get('resultUrl', {}).get('jsonUrl')
        print('JSON URL:', json_url)
        if json_url:
            resp = await client.get(json_url)
            with open('scripts/raw_prescription_response.json', 'w', encoding='utf-8') as f:
                f.write(resp.text)
            print('Saved raw response!')
            first_line = json.loads(resp.text.strip().split('\n')[0])
            pruned = first_line.get('result', {}).get('layoutParsingResults', [{}])[0].get('prunedResult', {})
            parsing_list = pruned.get('parsing_res_list', [])
            print(f'Parsing list count: {len(parsing_list)}')
            for i, p in enumerate(parsing_list):
                print(f"Item {i}: id={p.get('block_id')}, label={p.get('block_label')}, order={p.get('block_order')}")

if __name__ == '__main__':
    asyncio.run(check())
