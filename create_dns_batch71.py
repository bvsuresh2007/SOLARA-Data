import requests, json, time, sys
from dotenv import dotenv_values
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
s.mount('https://', HTTPAdapter(max_retries=retries))
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

# Get Shopify creds
r0 = s.get(f'{BASE}/api/resource/Shopify Setting/Shopify Setting', timeout=15)
sdata = r0.json()['data']
shop_url = sdata['shopify_url']
shop_token = sdata['password']
shopify_s = requests.Session()
shopify_s.mount('https://', HTTPAdapter(max_retries=retries))
shopify_s.headers.update({'X-Shopify-Access-Token': shop_token, 'Content-Type': 'application/json'})

# 71 orders (excluding cancelled SOL1194633)
so_list = [
    ('SOL1194660', 'SHP27-00774'), ('SOL1194654', 'SHP27-00768'), ('SOL1194651', 'SHP27-00765'),
    ('SOL1194647', 'SHP27-00761'), ('SOL1194645', 'SHP27-00759'), ('SOL1194644', 'SHP27-00758'),
    ('SOL1194643', 'SHP27-00757'), ('SOL1194639', 'SHP27-00753'), ('SOL1194637', 'SHP27-00751'),
    ('SOL1194635', 'SHP27-00749'), ('SOL1194623', 'SHP27-00737'), ('SOL1194622', 'SHP27-00736'),
    ('SOL1194619', 'SHP27-00733'), ('SOL1194616', 'SHP27-00730'), ('SOL1194612', 'SHP27-00726'),
    ('SOL1194610', 'SHP27-00724'), ('SOL1194604', 'SHP27-00718'), ('SOL1194603', 'SHP27-00717'),
    ('SOL1194602', 'SHP27-00716'), ('SOL1194600', 'SHP27-00714'), ('SOL1194597', 'SHP27-00711'),
    ('SOL1194595', 'SHP27-00709'), ('SOL1194594', 'SHP27-00708'), ('SOL1194591', 'SHP27-00705'),
    ('SOL1194590', 'SHP27-00704'), ('SOL1194588', 'SHP27-00702'), ('SOL1194587', 'SHP27-00701'),
    ('SOL1194585', 'SHP27-00699'), ('SOL1194583', 'SHP27-00697'), ('SOL1194580', 'SHP27-00694'),
    ('SOL1194577', 'SHP27-00691'), ('SOL1194575', 'SHP27-00689'), ('SOL1194574', 'SHP27-00688'),
    ('SOL1194571', 'SHP27-00685'), ('SOL1194566', 'SHP27-00680'), ('SOL1194562', 'SHP27-00676'),
    ('SOL1194657', 'SHP27-00771'), ('SOL1194632', 'SHP27-00746'), ('SOL1194601', 'SHP27-00715'),
    ('SOL1194564', 'SHP27-00678'), ('SOL1194636', 'SHP27-00750'), ('SOL1194593', 'SHP27-00707'),
    ('SOL1194582', 'SHP27-00696'), ('SOL1194560', 'SHP27-00674'), ('SOL1194653', 'SHP27-00767'),
    ('SOL1194625', 'SHP27-00739'), ('SOL1194565', 'SHP27-00679'), ('SOL1194572', 'SHP27-00686'),
    ('SOL1194626', 'SHP27-00740'), ('SOL1194605', 'SHP27-00719'), ('SOL1194586', 'SHP27-00700'),
    ('SOL1194634', 'SHP27-00748'), ('SOL1194581', 'SHP27-00695'), ('SOL1194663', 'SHP27-00777'),
    ('SOL1194579', 'SHP27-00693'), ('SOL1194641', 'SHP27-00755'), ('SOL1194661', 'SHP27-00775'),
    ('SOL1194656', 'SHP27-00770'), ('SOL1194655', 'SHP27-00769'), ('SOL1194658', 'SHP27-00772'),
    ('SOL1194627', 'SHP27-00741'), ('SOL1194618', 'SHP27-00732'), ('SOL1194617', 'SHP27-00731'),
    ('SOL1194614', 'SHP27-00728'), ('SOL1194471', 'SHP27-00585'), ('SOL1194621', 'SHP27-00735'),
    ('SOL1194606', 'SHP27-00720'), ('SOL1194599', 'SHP27-00713'), ('SOL1194608', 'SHP27-00722'),
    ('SOL1194542', 'SHP27-00656'), ('SOL1194426', 'SHP27-00534'),
]

total = len(so_list)
print(f'Processing {total} orders in batches...\n')

# Get shopify order IDs for all orders (batch lookup)
print('Step 1: Getting Shopify order IDs...')
shopify_ids = {}  # oid -> shopify_id
for so_oid, so_name in so_list:
    r = s.get(f'{BASE}/api/resource/Sales Order/{so_name}', params={
        'fields': json.dumps(['shopify_order_id'])
    }, timeout=15)
    if r.status_code == 200:
        sid = r.json()['data'].get('shopify_order_id', '') or ''
        if sid:
            shopify_ids[so_oid] = sid
    time.sleep(0.1)

# For missing ones, lookup on Shopify
missing = [oid for oid, _ in so_list if oid not in shopify_ids]
if missing:
    print(f'  Looking up {len(missing)} missing Shopify IDs...')
    for oid in missing:
        try:
            r = shopify_s.get(f'https://{shop_url}/admin/api/2024-01/orders.json', params={
                'name': oid, 'status': 'any', 'limit': 1
            }, timeout=15)
            orders = r.json().get('orders', [])
            if orders:
                shopify_ids[oid] = str(orders[0]['id'])
        except:
            pass
        time.sleep(0.2)

print(f'  Got {len(shopify_ids)}/{total} Shopify IDs')

# Check which SOs already have submitted DNs
print('\nStep 2: Checking existing DNs...')
skip_sos = set()
for oid, so_name in so_list:
    r = s.get(f'{BASE}/api/resource/Delivery Note', params={
        'filters': json.dumps([['Delivery Note Item', 'against_sales_order', '=', so_name], ['docstatus', '=', 1]]),
        'fields': json.dumps(['name', 'awb_number']),
        'limit_page_length': 1
    }, timeout=15)
    dns = r.json().get('data', [])
    if dns:
        awb = dns[0].get('awb_number', '') or ''
        print(f'  {oid} ({so_name}): already has submitted DN {dns[0]["name"]} | AWB: {awb or "none"}')
        skip_sos.add(oid)
    time.sleep(0.1)

to_process = [(oid, so) for oid, so in so_list if oid not in skip_sos]
print(f'  {len(to_process)} orders need DN creation (skipping {len(skip_sos)})')

# Process in batches of 10
BATCH_SIZE = 10
results = {
    'success': [],      # (oid, so, dn, awb, courier)
    'no_awb': [],       # (oid, so, dn)
    'stock_err': [],    # (oid, so, dn_or_empty, error)
    'failed': [],       # (oid, so, error)
    'skipped': [],      # (oid, so, reason)
}

for batch_start in range(0, len(to_process), BATCH_SIZE):
    batch = to_process[batch_start:batch_start + BATCH_SIZE]
    batch_num = batch_start // BATCH_SIZE + 1
    total_batches = (len(to_process) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f'\n=== Batch {batch_num}/{total_batches} ({len(batch)} orders) ===')

    for idx, (oid, so_name) in enumerate(batch, 1):
        global_idx = batch_start + idx
        shopify_id = shopify_ids.get(oid, '')
        print(f'  [{global_idx}/{len(to_process)}] {oid} ({so_name})... ', end='', flush=True)

        try:
            # Create DN from SO
            r1 = s.post(
                f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
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

            # Save DN
            r2 = s.post(f'{BASE}/api/resource/Delivery Note', json=dn_data, timeout=30)
            if r2.status_code != 200:
                print(f'SAVE FAILED')
                results['failed'].append((oid, so_name, f'save: {r2.text[:100]}'))
                time.sleep(0.5)
                continue

            dn_name = r2.json()['data']['name']

            # Submit DN
            r3 = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={'docstatus': 1}, timeout=30)
            if r3.status_code != 200:
                err = r3.text
                if 'NegativeStockError' in err:
                    print(f'STOCK ERROR ({dn_name})')
                    results['stock_err'].append((oid, so_name, dn_name, 'NegativeStockError'))
                else:
                    print(f'SUBMIT FAILED ({dn_name})')
                    results['failed'].append((oid, so_name, f'submit {dn_name}: {err[:100]}'))
                time.sleep(0.5)
                continue

            # Check AWB (quick check)
            time.sleep(2)
            r4 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner', 'shipment_status'])
            }, timeout=15)
            d = r4.json()['data']
            awb = d.get('awb_number', '') or ''
            courier = d.get('courier_partner', '') or ''

            if awb:
                print(f'OK -> {dn_name} | AWB: {awb} | {courier}')
                results['success'].append((oid, so_name, dn_name, awb, courier))
            else:
                print(f'OK -> {dn_name} | no AWB yet')
                results['no_awb'].append((oid, so_name, dn_name))

        except Exception as e:
            print(f'ERROR: {e}')
            results['failed'].append((oid, so_name, str(e)[:100]))

        time.sleep(0.3)

    # Pause between batches
    if batch_start + BATCH_SIZE < len(to_process):
        print(f'  Batch done. Pausing 3s...')
        time.sleep(3)

# Re-check pending AWBs
if results['no_awb']:
    print(f'\n=== Re-checking {len(results["no_awb"])} DNs for AWB (waiting 15s) ===')
    time.sleep(15)
    still_pending = []
    for oid, so_name, dn_name in results['no_awb']:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {oid} ({dn_name}): AWB {awb} | {courier}')
            results['success'].append((oid, so_name, dn_name, awb, courier))
        else:
            still_pending.append((oid, so_name, dn_name))
        time.sleep(0.1)
    results['no_awb'] = still_pending

    # One more round if still pending
    if results['no_awb']:
        print(f'  Still {len(results["no_awb"])} pending. Waiting 15s more...')
        time.sleep(15)
        final_pending = []
        for oid, so_name, dn_name in results['no_awb']:
            r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner'])
            }, timeout=15)
            d = r.json()['data']
            awb = d.get('awb_number', '') or ''
            courier = d.get('courier_partner', '') or ''
            if awb:
                print(f'  {oid} ({dn_name}): AWB {awb} | {courier}')
                results['success'].append((oid, so_name, dn_name, awb, courier))
            else:
                final_pending.append((oid, so_name, dn_name))
            time.sleep(0.1)
        results['no_awb'] = final_pending

# Summary
print(f'\n{"="*120}')
print(f'SUMMARY')
print(f'{"="*120}')
print(f'Total processed:    {len(to_process)}')
print(f'DN + AWB:           {len(results["success"])}')
print(f'DN, no AWB:         {len(results["no_awb"])}')
print(f'Stock error:        {len(results["stock_err"])}')
print(f'Failed:             {len(results["failed"])}')
print(f'Already had DN:     {len(skip_sos)}')

if results['success']:
    print(f'\n--- Success ({len(results["success"])}) ---')
    print(f'{"Order":<14} {"SO":<16} {"DN":<18} {"AWB":<18} {"Courier"}')
    for oid, so, dn, awb, courier in results['success']:
        print(f'{oid:<14} {so:<16} {dn:<18} {awb:<18} {courier}')

if results['no_awb']:
    print(f'\n--- No AWB ({len(results["no_awb"])}) ---')
    for oid, so, dn in results['no_awb']:
        print(f'  {oid} ({so}) -> {dn}')

if results['stock_err']:
    print(f'\n--- Stock Error ({len(results["stock_err"])}) ---')
    for oid, so, dn, err in results['stock_err']:
        print(f'  {oid} ({so}) -> {dn}')

if results['failed']:
    print(f'\n--- Failed ({len(results["failed"])}) ---')
    for oid, so, err in results['failed']:
        print(f'  {oid} ({so}): {err}')

print(f'\nDone!')
