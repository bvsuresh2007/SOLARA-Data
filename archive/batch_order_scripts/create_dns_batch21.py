import requests, json, time
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
retries = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
s.mount('https://', HTTPAdapter(max_retries=retries))
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

so_list = [
    ('SOL1194664', 'SHP27-00778'), ('SOL1194662', 'SHP27-00776'), ('SOL1194652', 'SHP27-00766'),
    ('SOL1194649', 'SHP27-00763'), ('SOL1194638', 'SHP27-00752'), ('SOL1194584', 'SHP27-00698'),
    ('SOL1194578', 'SHP27-00692'), ('SOL1194573', 'SHP27-00687'), ('SOL1194570', 'SHP27-00684'),
    ('SOL1194567', 'SHP27-00681'), ('SOL1194563', 'SHP27-00677'), ('SOL1194596', 'SHP27-00710'),
    ('SOL1194629', 'SHP27-00743'), ('SOL1194624', 'SHP27-00738'), ('SOL1194607', 'SHP27-00721'),
    ('SOL1194568', 'SHP27-00682'), ('SOL1194659', 'SHP27-00773'), ('SOL1194648', 'SHP27-00762'),
    ('SOL1194667', 'SHP27-00781'), ('SOL1194613', 'SHP27-00727'), ('SOL1194620', 'SHP27-00734'),
]

total = len(so_list)
print(f'Processing {total} orders...\n')

# Get shopify_order_ids
print('Getting Shopify IDs...')
shopify_ids = {}
for oid, so_name in so_list:
    r = s.get(f'{BASE}/api/resource/Sales Order/{so_name}', params={
        'fields': json.dumps(['shopify_order_id'])
    }, timeout=15)
    if r.status_code == 200:
        sid = r.json()['data'].get('shopify_order_id', '') or ''
        if sid:
            shopify_ids[oid] = sid
    time.sleep(0.1)
print(f'  Got {len(shopify_ids)}/{total} Shopify IDs')

results = {'success': [], 'stock_err': [], 'failed': []}

BATCH_SIZE = 10
for batch_start in range(0, total, BATCH_SIZE):
    batch = so_list[batch_start:batch_start + BATCH_SIZE]
    batch_num = batch_start // BATCH_SIZE + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f'\n=== Batch {batch_num}/{total_batches} ({len(batch)} orders) ===')

    for idx, (oid, so_name) in enumerate(batch, 1):
        global_idx = batch_start + idx
        shopify_id = shopify_ids.get(oid, '')
        print(f'  [{global_idx}/{total}] {oid} ({so_name})... ', end='', flush=True)

        try:
            r1 = s.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                        json={'source_name': so_name}, timeout=30)
            if r1.status_code != 200:
                print(f'MAKE FAILED')
                results['failed'].append((oid, so_name, f'make_dn: {r1.text[:100]}'))
                time.sleep(0.5)
                continue

            dn_data = r1.json().get('message', {})
            if shopify_id:
                dn_data['shopify_order_id'] = shopify_id
                dn_data['shopify_order_number'] = oid

            r2 = s.post(f'{BASE}/api/resource/Delivery Note', json=dn_data, timeout=30)
            if r2.status_code != 200:
                print(f'SAVE FAILED')
                results['failed'].append((oid, so_name, f'save: {r2.text[:100]}'))
                time.sleep(0.5)
                continue

            dn_name = r2.json()['data']['name']

            r3 = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={'docstatus': 1}, timeout=30)
            if r3.status_code != 200:
                err = r3.text
                if 'NegativeStockError' in err:
                    print(f'STOCK ERROR ({dn_name})')
                    results['stock_err'].append((oid, so_name, dn_name))
                else:
                    print(f'SUBMIT FAILED ({dn_name})')
                    results['failed'].append((oid, so_name, f'submit {dn_name}: {err[:100]}'))
                time.sleep(0.5)
                continue

            time.sleep(2)
            r4 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner'])
            }, timeout=15)
            d = r4.json()['data']
            awb = d.get('awb_number', '') or ''
            courier = d.get('courier_partner', '') or ''

            if awb:
                print(f'OK -> {dn_name} | AWB: {awb} | {courier}')
                results['success'].append((oid, so_name, dn_name, awb, courier))
            else:
                print(f'OK -> {dn_name} | no AWB yet')
                results['success'].append((oid, so_name, dn_name, '', ''))

        except Exception as e:
            print(f'ERROR: {e}')
            results['failed'].append((oid, so_name, str(e)[:100]))

        time.sleep(0.3)

    if batch_start + BATCH_SIZE < total:
        print(f'  Batch done. Pausing 3s...')
        time.sleep(3)

# Re-check missing AWBs
no_awb = [(oid, so, dn, awb, c) for oid, so, dn, awb, c in results['success'] if not awb]
if no_awb:
    print(f'\nRe-checking {len(no_awb)} DNs for AWB (waiting 15s)...')
    time.sleep(15)
    updated = []
    for oid, so, dn, _, _ in no_awb:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {oid} ({dn}): AWB {awb} | {courier}')
        updated.append((oid, so, dn, awb, courier))
        time.sleep(0.1)
    # Replace in results
    results['success'] = [(oid, so, dn, awb, c) for oid, so, dn, awb, c in results['success'] if awb] + updated

# Summary
print(f'\n{"="*100}')
print(f'SUMMARY: {len(results["success"])} success | {len(results["stock_err"])} stock error | {len(results["failed"])} failed')
print(f'{"="*100}')
print(f'{"#":<4} {"Order":<14} {"SO":<16} {"DN":<18} {"AWB":<18} {"Courier"}')
print('-' * 85)
for i, (oid, so, dn, awb, courier) in enumerate(results['success'], 1):
    print(f'{i:<4} {oid:<14} {so:<16} {dn:<18} {awb:<18} {courier}')

if results['stock_err']:
    print(f'\nStock Errors:')
    for oid, so, dn in results['stock_err']:
        print(f'  {oid} ({so}) -> {dn}')

if results['failed']:
    print(f'\nFailed:')
    for oid, so, err in results['failed']:
        print(f'  {oid} ({so}): {err}')

print(f'\nDone!')
