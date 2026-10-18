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

# SKUs that need stock
skus_needed = {
    'SOL-SLB-RBR-GKT-201': 1,
    'SOL-INS-WB-CP-SIP-405': 1,
    'SOL-JUC-AUG': 2,
    'SOL-INS-TUM-CPTOP-203': 1,
    'SOL-JUC-121-AUG': 1,
}

# Step 1: Get valuation rates from stock ledger
print('=== Getting valuation rates ===')
val_rates = {}
for sku in skus_needed:
    script = f"""sle = frappe.db.sql("SELECT valuation_rate FROM `tabStock Ledger Entry` WHERE item_code='{sku}' AND warehouse='Main Warehouse - WTBBPL' AND valuation_rate > 0 ORDER BY posting_date DESC, posting_time DESC LIMIT 1", as_dict=1)
frappe.response['message'] = str(sle[0]['valuation_rate']) if sle else '0'
"""
    msg = run_server_script(f'tmp_vr_{sku[-6:].replace("-","")}', script)
    rate = float(msg or '0')
    val_rates[sku] = rate
    print(f'  {sku}: Rs {rate}')

# Step 2: Create Material Receipts
print('\n=== Creating Material Receipts ===')
for sku, qty in skus_needed.items():
    rate = val_rates[sku]
    if rate == 0:
        print(f'  WARNING: {sku} has no valuation rate! Skipping.')
        continue

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

    # Submit MR
    r2 = requests.put(f'{BASE}/api/resource/Stock Entry/{mr_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r2.status_code == 200:
        print(f'  MR submitted!')
    else:
        print(f'  MR submit failed: {r2.status_code} {r2.text[:200]}')

time.sleep(2)

# Step 3: Retry submitting the 6 draft DNs
print('\n=== Retrying draft DN submissions ===')
draft_dns = [
    ('REP-2627-OTH-00050', 'neha rai', 'SHPDN27-16489'),
    ('REP-2627-SHP-00627', 'Shruti .', None),  # Need to recreate - 502 meant no DN saved
    ('REP-2627-SHP-00622', 'Vani Madhav', 'SHPDN27-16511'),
    ('REP-2627-OTH-00049', 'Srinivasulu Bhuvanagiri', 'SHPDN27-16514'),
    ('REP-2627-SHP-00637', 'Trushit Agrawal', 'SHPDN27-16515'),
    ('REP-2627-SHP-00644', 'Tulsiram Badgujar', 'SHPDN27-16516'),
]

results = []
for so_name, cust, dn_name in draft_dns:
    print(f'\n--- {so_name} ({cust}) ---')

    if dn_name is None:
        # Shruti - need to create DN from scratch (502 meant save failed)
        print(f'  Creating DN from SO...')
        r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
        so = r_so.json().get('data', {})
        addr_name = so.get('shipping_address_name', '')

        r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
            headers=H, params={'source_name': so_name}, timeout=15)
        if r_dn.status_code != 200:
            print(f'  make_delivery_note failed: {r_dn.status_code}')
            results.append((so_name, cust, '', '', 'FAIL'))
            continue
        dn_draft = r_dn.json().get('message', {})
        dn_draft['shipping_address_name'] = addr_name
        dn_draft['customer_address'] = addr_name
        dn_draft['is_replacement'] = 1
        for tax in dn_draft.get('taxes', []):
            if tax.get('item_wise_tax_detail') is None:
                tax['item_wise_tax_detail'] = '{}'
        for item in dn_draft.get('items', []):
            item.pop('item_tax_template', None)
        for key in ['__islocal', '__unsaved', 'amended_from']:
            dn_draft.pop(key, None)

        r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
        if r3.status_code != 200:
            print(f'  DN save failed: {r3.status_code} {r3.text[:200]}')
            results.append((so_name, cust, '', '', 'FAIL'))
            continue
        dn_name = r3.json().get('data', {}).get('name', '')
        print(f'  DN created: {dn_name}')

    # Submit DN
    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'  DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'  DN submitted (417 OK)!')
        else:
            print(f'  DN submit failed: {r4.text[:300]}')
            results.append((so_name, cust, dn_name, '', 'SUBMIT_FAIL'))
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((so_name, cust, dn_name, '', 'SUBMIT_FAIL'))
        continue

    # Check AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')
    print(f'  AWB={awb} via {courier}')
    results.append((so_name, cust, dn_name, awb, courier))

print(f'\n\n{"="*80}')
print('RETRY SUMMARY')
print(f'{"="*80}')
for so_name, cust, dn, awb, status in results:
    print(f'  {so_name:<25} {cust:<28} DN={dn:<18} AWB={awb:<18} {status}')
