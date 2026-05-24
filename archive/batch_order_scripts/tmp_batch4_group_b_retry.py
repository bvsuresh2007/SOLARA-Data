import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# SOL1204873 - Mansoor - DN SHPDN27-13886 created but submit failed (PostingTime race)
# DN is draft, just retry submit
dn = 'SHPDN27-13886'

print(f'Checking DN {dn}...')
r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
    params={'fields': json.dumps(['name','docstatus','awb_number','courier_partner','customer_name','shopify_order_id','shopify_order_number'])},
    timeout=15)
d = r.json().get('data', {})
print(f'  ds={d.get("docstatus")} | AWB={d.get("awb_number","")} | {d.get("customer_name","")}')

if d.get('docstatus') == 0:
    print(f'  Submitting...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn}',
        headers=H, json={'docstatus': 1}, timeout=60)
    if r_sub.status_code == 200:
        print(f'  ✓ Submitted')
        time.sleep(3)
        r2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
            params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
        d2 = r2.json().get('data', {})
        print(f'  AWB={d2.get("awb_number","")} | Courier={d2.get("courier_partner","")}')
    else:
        print(f'  FAIL: {r_sub.status_code} {r_sub.text[:300]}')
elif d.get('docstatus') == 1:
    print(f'  Already submitted! AWB={d.get("awb_number","")}')
