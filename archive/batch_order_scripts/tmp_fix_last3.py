import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200: return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(6)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    if exc:
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

# Get valuation rates for the 3 remaining SKUs via a single server script
print('=== Getting valuation rates ===')
script = """results = []
for sku in ['SOL-SLB-RBR-GKT-201', 'SOL-JUC-FILTER', 'SOL-INS-TUM-CPTOP-203']:
    sle = frappe.db.sql("SELECT valuation_rate FROM `tabStock Ledger Entry` WHERE item_code=%s AND warehouse='Main Warehouse - WTBBPL' AND valuation_rate > 0 ORDER BY posting_date DESC, posting_time DESC LIMIT 1", sku, as_dict=1)
    rate = str(sle[0]['valuation_rate']) if sle else '0'
    results.append(sku + '|' + rate)
frappe.response['message'] = ';;'.join(results)
"""
msg = run_server_script('tmp_vr_3skus', script)
val_rates = {}
if msg:
    for line in msg.split(';;'):
        parts = line.split('|')
        if len(parts) == 2:
            val_rates[parts[0]] = float(parts[1])
            print(f'  {parts[0]}: Rs {parts[1]}')

# For SKUs with 0 valuation, check if they're components (spare parts) - use Rs 1 as token
skus_needed = {
    'SOL-SLB-RBR-GKT-201': 1,   # neha rai
    'SOL-JUC-FILTER': 1,         # Srinivasulu (SO also needs SOL-JUC-AUG x2 but that was already MR'd)
    'SOL-INS-TUM-CPTOP-203': 1,  # Trushit
}

print('\n=== Creating Material Receipts ===')
for sku, qty in skus_needed.items():
    rate = val_rates.get(sku, 0)
    if rate == 0:
        rate = 1.0  # Token rate for spare parts with no history
        print(f'  {sku}: no val rate found, using Rs 1 token')

    mr_payload = {
        'stock_entry_type': 'Material Receipt',
        'to_warehouse': 'Main Warehouse - WTBBPL',
        'items': [{
            'item_code': sku,
            'qty': qty,
            't_warehouse': 'Main Warehouse - WTBBPL',
            'basic_rate': rate,
            'expense_account': 'Stock Adjustment - WTBBPL',
        }],
    }
    r = requests.post(f'{BASE}/api/resource/Stock Entry', headers=H, json=mr_payload, timeout=30)
    if r.status_code != 200:
        print(f'  MR create failed for {sku}: {r.status_code} {r.text[:200]}')
        continue
    mr_name = r.json().get('data', {}).get('name', '')
    print(f'  MR created: {mr_name} ({sku} x{qty} @ Rs {rate})')
    r2 = requests.put(f'{BASE}/api/resource/Stock Entry/{mr_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r2.status_code == 200:
        print(f'  MR submitted!')
    else:
        print(f'  MR submit failed: {r2.status_code} {r2.text[:200]}')

time.sleep(2)

# Retry the 3 remaining DNs
print('\n=== Retrying DN submissions ===')
draft_dns = [
    ('REP-2627-OTH-00050', 'neha rai', 'SHPDN27-16489'),
    ('REP-2627-OTH-00049', 'Srinivasulu Bhuvanagiri', 'SHPDN27-16514'),
    ('REP-2627-SHP-00637', 'Trushit Agrawal', 'SHPDN27-16515'),
]

for so_name, cust, dn_name in draft_dns:
    print(f'\n--- {so_name} ({cust}) ---')
    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'  DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'  DN submitted (417 OK)!')
        else:
            print(f'  DN submit STILL failed: {r4.text[:300]}')
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        continue

    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')
    print(f'  AWB={awb} via {courier}')

print('\nDONE')
