import os, requests, json
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
    params={'filters': json.dumps([['creation','>','2026-05-04 12:00:00']]),
            'fields': json.dumps(['name','method','error','creation']),
            'order_by': 'creation desc', 'limit_page_length': 5}, timeout=15)
errs = r.json().get('data', [])

for e in errs:
    creation = e.get('creation', '')
    method = e.get('method', '')
    error = str(e.get('error', ''))[:400]
    print(f"--- {creation} ---")
    print(f"Method: {method}")
    print(f"Error: {error}")
    print()
