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
    ('SOL1194949', 'SHP27-01099'), ('SOL1194947', 'SHP27-01097'), ('SOL1194940', 'SHP27-01090'),
    ('SOL1194938', 'SHP27-01088'), ('SOL1194936', 'SHP27-01086'), ('SOL1194935', 'SHP27-01085'),
    ('SOL1194933', 'SHP27-01083'), ('SOL1194932', 'SHP27-01082'), ('SOL1194931', 'SHP27-01081'),
    ('SOL1194924', 'SHP27-01071'), ('SOL1194923', 'SHP27-01070'), ('SOL1194921', 'SHP27-01066'),
    ('SOL1194917', 'SHP27-01061'), ('SOL1194915', 'SHP27-01059'), ('SOL1194914', 'SHP27-01058'),
    ('SOL1194913', 'SHP27-01057'), ('SOL1194909', 'SHP27-01052'), ('SOL1194908', 'SHP27-01051'),
    ('SOL1194905', 'SHP27-01048'), ('SOL1194904', 'SHP27-01047'), ('SOL1194903', 'SHP27-01046'),
    ('SOL1194901', 'SHP27-01044'), ('SOL1194899', 'SHP27-01042'), ('SOL1194896', 'SHP27-01039'),
    ('SOL1194883', 'SHP27-01026'), ('SOL1194882', 'SHP27-01025'), ('SOL1194880', 'SHP27-01023'),
    ('SOL1194874', 'SHP27-01017'), ('SOL1194873', 'SHP27-01016'), ('SOL1194871', 'SHP27-01014'),
    ('SOL1194867', 'SHP27-01010'), ('SOL1194857', 'SHP27-01000'), ('SOL1194856', 'SHP27-00999'),
    ('SOL1194854', 'SHP27-00997'), ('SOL1194851', 'SHP27-00994'), ('SOL1194850', 'SHP27-00993'),
    ('SOL1194847', 'SHP27-00990'), ('SOL1194845', 'SHP27-00988'), ('SOL1194844', 'SHP27-00987'),
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
            # Check existing DN first
            r0 = s.get(f'{BASE}/api/resource/Delivery Note', params={
                'filters': json.dumps([['Delivery Note Item', 'against_sales_order', '=', so_name], ['docstatus', '!=', 2]]),
                'fields': json.dumps(['name', 'docstatus', 'awb_number', 'courier_partner']),
                'limit_page_length': 5
            }, timeout=15)
            existing = r0.json().get('data', [])
            if existing:
                dn = existing[0]
                if dn['docstatus'] == 1:
                    awb = dn.get('awb_number', '') or ''
                    courier = dn.get('courier_partner', '') or ''
                    print(f'ALREADY EXISTS -> {dn["name"]} | AWB: {awb or "none"} | {courier}')
                    results['success'].append((oid, so_name, dn['name'], awb, courier))
                    continue

            r1 = s.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                        json={'source_name': so_name}, timeout=30)
            if r1.status_code != 200:
                print(f'MAKE FAILED')
                results['failed'].append((oid, so_name, f'make_dn: {r1.text[:100]}'))
                time.sleep(0.5)
                continue

            dn_data = r1.json().get('message', {})

            # Check if items are empty
            if not dn_data.get('items'):
                print(f'NO ITEMS (already delivered?)')
                results['failed'].append((oid, so_name, 'make_dn returned 0 items'))
                time.sleep(0.3)
                continue

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
    results['success'] = [(oid, so, dn, awb, c) for oid, so, dn, awb, c in results['success'] if awb] + updated

# Second re-check after 30s
no_awb2 = [(oid, so, dn, awb, c) for oid, so, dn, awb, c in results['success'] if not awb]
if no_awb2:
    print(f'\nRe-checking {len(no_awb2)} DNs for AWB (waiting 30s)...')
    time.sleep(30)
    updated2 = []
    for oid, so, dn, _, _ in no_awb2:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {oid} ({dn}): AWB {awb} | {courier}')
        updated2.append((oid, so, dn, awb, courier))
        time.sleep(0.1)
    results['success'] = [(oid, so, dn, awb, c) for oid, so, dn, awb, c in results['success'] if awb] + updated2

# Summary
print(f'\n{"="*100}')
print(f'SUMMARY: {len(results["success"])} success | {len(results["stock_err"])} stock error | {len(results["failed"])} failed')
print(f'{"="*100}')
print(f'{"#":<4} {"Order":<14} {"SO":<16} {"DN":<18} {"AWB":<22} {"Courier"}')
print('-' * 90)
for i, (oid, so, dn, awb, courier) in enumerate(results['success'], 1):
    print(f'{i:<4} {oid:<14} {so:<16} {dn:<18} {(awb or "NO AWB"):<22} {courier}')

if results['stock_err']:
    print(f'\nStock Errors:')
    for oid, so, dn in results['stock_err']:
        print(f'  {oid} ({so}) -> {dn}')

if results['failed']:
    print(f'\nFailed:')
    for oid, so, err in results['failed']:
        print(f'  {oid} ({so}): {err}')

print(f'\nDone!')
