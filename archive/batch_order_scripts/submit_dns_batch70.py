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
    'SHPDN27-01065','SHPDN27-01066','SHPDN27-01067','SHPDN27-01068','SHPDN27-01069',
    'SHPDN27-01070','SHPDN27-01071','SHPDN27-01072','SHPDN27-01073','SHPDN27-01074',
    'SHPDN27-01075','SHPDN27-01076','SHPDN27-01077','SHPDN27-01078','SHPDN27-01079',
    'SHPDN27-01080','SHPDN27-01081','SHPDN27-01082','SHPDN27-01083','SHPDN27-01084',
    'SHPDN27-01085','SHPDN27-01086','SHPDN27-01087','SHPDN27-01088','SHPDN27-01089',
    'SHPDN27-01090','SHPDN27-01091','SHPDN27-01092','SHPDN27-01093','SHPDN27-01094',
    'SHPDN27-01095','SHPDN27-01096','SHPDN27-01097','SHPDN27-01098','SHPDN27-01099',
    'SHPDN27-01100','SHPDN27-01101','SHPDN27-01102','SHPDN27-01103','SHPDN27-01104',
    'SHPDN27-01105','SHPDN27-01106','SHPDN27-01107','SHPDN27-01108','SHPDN27-01109',
    'SHPDN27-01110','SHPDN27-01111','SHPDN27-01112','SHPDN27-01113','SHPDN27-01114',
    'SHPDN27-01115','SHPDN27-01116','SHPDN27-01117','SHPDN27-01118','SHPDN27-01119',
    'SHPDN27-01120','SHPDN27-01121','SHPDN27-01122','SHPDN27-01123','SHPDN27-01124',
    'SHPDN27-01125','SHPDN27-01126','SHPDN27-01127','SHPDN27-01128','SHPDN27-01129',
    'SHPDN27-01130','SHPDN27-01131','SHPDN27-01132','SHPDN27-01133','SHPDN27-01134',
]

total = len(dns)
print(f'Processing {total} DNs...\n')

results = {'success': [], 'stock_err': [], 'failed': [], 'already': []}

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
            # Check current status
            r0 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['docstatus', 'awb_number', 'courier_partner'])
            }, timeout=15)
            if r0.status_code != 200:
                print(f'NOT FOUND')
                results['failed'].append((dn_name, 'DN not found'))
                continue

            d0 = r0.json()['data']
            if d0['docstatus'] == 1:
                awb = d0.get('awb_number', '') or ''
                courier = d0.get('courier_partner', '') or ''
                if awb:
                    print(f'ALREADY SUBMITTED | AWB: {awb} | {courier}')
                    results['already'].append((dn_name, awb, courier))
                else:
                    print(f'ALREADY SUBMITTED | no AWB')
                    results['already'].append((dn_name, '', ''))
                continue

            # Submit
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
all_no_awb = [(dn, a, c) for dn, a, c in results['success'] if not a] + [(dn, a, c) for dn, a, c in results['already'] if not a]
if all_no_awb:
    print(f'\nRe-checking {len(all_no_awb)} DNs for AWB (waiting 15s)...')
    time.sleep(15)
    for dn_name, _, _ in all_no_awb:
        r = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r.json()['data']
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  {dn_name}: AWB {awb} | {courier}')
            # Update in results
            results['success'] = [(dn, awb if dn == dn_name else a, courier if dn == dn_name else c) for dn, a, c in results['success']]
            results['already'] = [(dn, awb if dn == dn_name else a, courier if dn == dn_name else c) for dn, a, c in results['already']]
        time.sleep(0.1)

# Summary
all_results = results['success'] + results['already']
with_awb = [(dn, a, c) for dn, a, c in all_results if a]
no_awb_final = [(dn, a, c) for dn, a, c in all_results if not a]

print(f'\n{"="*100}')
print(f'SUMMARY: {len(results["success"])} submitted | {len(results["already"])} already done | {len(results["stock_err"])} stock error | {len(results["failed"])} failed')
print(f'AWBs: {len(with_awb)}/{len(all_results)}')
print(f'{"="*100}')
print(f'{"#":<4} {"DN":<18} {"AWB":<22} {"Courier":<15} {"Note"}')
print('-' * 80)
i = 1
for dn, awb, courier in results['success']:
    print(f'{i:<4} {dn:<18} {(awb or "NO AWB"):<22} {courier:<15} {"submitted"}')
    i += 1
for dn, awb, courier in results['already']:
    print(f'{i:<4} {dn:<18} {(awb or "NO AWB"):<22} {courier:<15} {"already submitted"}')
    i += 1

if results['stock_err']:
    print(f'\nStock Errors:')
    for dn in results['stock_err']:
        print(f'  {dn}')

if results['failed']:
    print(f'\nFailed:')
    for dn, err in results['failed']:
        print(f'  {dn}: {err}')

print(f'\nDone!')
