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

dns = [
    'SHPDN27-01135','SHPDN27-01136','SHPDN27-01137','SHPDN27-01138','SHPDN27-01139',
    'SHPDN27-01140','SHPDN27-01141','SHPDN27-01142','SHPDN27-01143','SHPDN27-01144',
    'SHPDN27-01145','SHPDN27-01146','SHPDN27-01147','SHPDN27-01148','SHPDN27-01149',
    'SHPDN27-01150','SHPDN27-01151','SHPDN27-01152','SHPDN27-01153','SHPDN27-01154',
    'SHPDN27-01155','SHPDN27-01156','SHPDN27-01157','SHPDN27-01158','SHPDN27-01159',
    'SHPDN27-01160','SHPDN27-01161','SHPDN27-01162','SHPDN27-01163','SHPDN27-01164',
    'SHPDN27-01165','SHPDN27-01166','SHPDN27-01167','SHPDN27-01168','SHPDN27-01169',
    'SHPDN27-01170','SHPDN27-01171','SHPDN27-01172','SHPDN27-01173','SHPDN27-01174',
    'SHPDN27-01175','SHPDN27-01176','SHPDN27-01177','SHPDN27-01178','SHPDN27-01179',
    'SHPDN27-01180','SHPDN27-01181','SHPDN27-01182','SHPDN27-01183','SHPDN27-01184',
    'SHPDN27-01185','SHPDN27-01186','SHPDN27-01187','SHPDN27-01188','SHPDN27-01189',
    'SHPDN27-01190','SHPDN27-01191','SHPDN27-01192','SHPDN27-01193','SHPDN27-01194',
    'SHPDN27-01195','SHPDN27-01196',
]

total = len(dns)
print(f'Processing {total} DNs...\n')

results = {'success': [], 'stock_err': [], 'failed': []}

BATCH_SIZE = 10
for batch_start in range(0, total, BATCH_SIZE):
    batch = dns[batch_start:batch_start + BATCH_SIZE]
    batch_num = batch_start // BATCH_SIZE + 1
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f'=== Batch {batch_num}/{total_batches} ({len(batch)} DNs) ===')

    for idx, dn_name in enumerate(batch, 1):
        global_idx = batch_start + idx
        print(f'  [{global_idx}/{total}] {dn_name}... ', end='', flush=True)

        try:
            r1 = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={'docstatus': 1}, timeout=30)
            if r1.status_code != 200:
                err = r1.text
                if 'NegativeStockError' in err:
                    print(f'STOCK ERROR')
                    results['stock_err'].append(dn_name)
                else:
                    print(f'SUBMIT FAILED: {err[:120]}')
                    results['failed'].append((dn_name, err[:150]))
                time.sleep(0.5)
                continue

            time.sleep(2)
            r2 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner'])
            }, timeout=15)
            d = r2.json()['data']
            awb = d.get('awb_number', '') or ''
            courier = d.get('courier_partner', '') or ''
            if awb:
                print(f'OK | AWB: {awb} | {courier}')
            else:
                print(f'OK | no AWB yet')
            results['success'].append((dn_name, awb, courier))

        except Exception as e:
            print(f'ERROR: {e}')
            results['failed'].append((dn_name, str(e)[:100]))

        time.sleep(0.3)

    if batch_start + BATCH_SIZE < total:
        print(f'  Batch done. Pausing 3s...')
        time.sleep(3)

# Re-check missing AWBs
no_awb = [(dn, a, c) for dn, a, c in results['success'] if not a]
if no_awb:
    print(f'\nRe-checking {len(no_awb)} DNs for AWB (waiting 15s)...')
    time.sleep(15)
    updated = []
    for dn_name, _, _ in no_awb:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {dn_name}: AWB {awb} | {courier}')
        updated.append((dn_name, awb, courier))
        time.sleep(0.1)
    results['success'] = [(dn, a, c) for dn, a, c in results['success'] if a] + updated

# Second re-check
no_awb2 = [(dn, a, c) for dn, a, c in results['success'] if not a]
if no_awb2:
    print(f'\nRe-checking {len(no_awb2)} DNs for AWB (waiting 30s)...')
    time.sleep(30)
    updated2 = []
    for dn_name, _, _ in no_awb2:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {dn_name}: AWB {awb} | {courier}')
        updated2.append((dn_name, awb, courier))
        time.sleep(0.1)
    results['success'] = [(dn, a, c) for dn, a, c in results['success'] if a] + updated2

# Summary
with_awb = [(dn, a, c) for dn, a, c in results['success'] if a]
no_awb_final = [(dn, a, c) for dn, a, c in results['success'] if not a]

print(f'\n{"="*100}')
print(f'SUMMARY: {len(results["success"])} submitted | {len(results["stock_err"])} stock error | {len(results["failed"])} failed')
print(f'AWBs: {len(with_awb)}/{len(results["success"])}')
print(f'{"="*100}')
print(f'{"#":<4} {"DN":<18} {"AWB":<22} {"Courier"}')
print('-' * 60)
for i, (dn, awb, courier) in enumerate(results['success'], 1):
    print(f'{i:<4} {dn:<18} {(awb or "NO AWB"):<22} {courier}')

if results['stock_err']:
    print(f'\nStock Errors:')
    for dn in results['stock_err']:
        print(f'  {dn}')

if results['failed']:
    print(f'\nFailed:')
    for dn, err in results['failed']:
        print(f'  {dn}: {err}')

print(f'\nDone!')
