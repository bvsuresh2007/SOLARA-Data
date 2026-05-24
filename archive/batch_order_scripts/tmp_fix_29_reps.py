import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

reps = [
    'REP-2627-SHP-00584','REP-2627-SHP-00585','REP-2627-SHP-00586','REP-2627-SHP-00587',
    'REP-2627-SHP-00588','REP-2627-SHP-00589','REP-2627-SHP-00590','REP-2627-SHP-00591',
    'REP-2627-SHP-00592','REP-2627-SHP-00593','REP-2627-SHP-00594','REP-2627-SHP-00595',
    'REP-2627-SHP-00596','REP-2627-SHP-00597','REP-2627-SHP-00598','REP-2627-SHP-00599',
    'REP-2627-SHP-00600','REP-2627-SHP-00601','REP-2627-SHP-00602','REP-2627-SHP-00603',
    'REP-2627-SHP-00604','REP-2627-SHP-00605','REP-2627-SHP-00606','REP-2627-SHP-00607',
    'REP-2627-SHP-00608','REP-2627-SHP-00609','REP-2627-OTH-00046','REP-2627-OTH-00047',
    'REP-2627-OTH-00048',
]

results = []

for so_name in reps:
    print(f'\n{"="*60}')
    print(f'=== {so_name} ===')

    # Get SO details
    r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    if r.status_code != 200:
        print(f'  SO NOT FOUND')
        results.append((so_name, 'SO_NOT_FOUND', '', '', ''))
        continue
    so = r.json().get('data', {})
    cust = so.get('customer', '')
    shipping_addr = so.get('shipping_address_name', '')
    cust_addr = so.get('customer_address', '')
    taxes = so.get('taxes_and_charges', '')
    items = ', '.join([i.get('item_code','') + ' x' + str(int(i.get('qty',1))) for i in so.get('items', [])])
    print(f'  {cust} | {items} | Shipping: {shipping_addr}')

    if not shipping_addr:
        print(f'  ERROR: No shipping_address_name on SO')
        results.append((so_name, 'NO_SHIPPING_ADDR', '', '', cust))
        continue

    # Make DN from SO
    r2 = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r2.status_code != 200:
        print(f'  make_delivery_note failed: {r2.status_code} {r2.text[:200]}')
        results.append((so_name, 'MAKE_DN_FAIL', '', '', cust))
        continue

    dn_draft = r2.json().get('message', {})
    dn_draft['is_replacement'] = 1
    dn_draft['shipping_address_name'] = shipping_addr
    dn_draft['customer_address'] = cust_addr or shipping_addr
    dn_draft['taxes'] = []
    dn_draft['taxes_and_charges'] = taxes
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    # Save DN
    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        print(f'  DN save failed: {r3.status_code} {r3.text[:300]}')
        results.append((so_name, 'DN_SAVE_FAIL', '', '', cust))
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
            err = r4.text[:300]
            print(f'  DN submit failed: {err}')
            # Check if stock issue
            if 'NegativeStockError' in err:
                results.append((so_name, 'NO_STOCK', dn_name, '', cust))
            else:
                results.append((so_name, 'DN_SUBMIT_FAIL', dn_name, '', cust))
            continue
    else:
        err = r4.text[:300]
        print(f'  DN submit failed: {r4.status_code} {err}')
        if 'NegativeStockError' in err:
            results.append((so_name, 'NO_STOCK', dn_name, '', cust))
        else:
            results.append((so_name, 'DN_SUBMIT_FAIL', dn_name, '', cust))
        continue

    # Check AWB (Clickpost auto-fires on replacement DN submit)
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number','courier_partner','docstatus'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')
    print(f'  AWB={awb} | {courier}')
    results.append((so_name, 'OK', dn_name, f'{awb} ({courier})', cust))
    time.sleep(0.5)

print(f'\n\n{"="*80}')
print(f'SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] != 'OK']
for r in ok:
    print(f'  OK       {r[0]} | {r[4]} | {r[2]} | {r[3]}')
for r in fail:
    print(f'  {r[1]:10s} {r[0]} | {r[4]} | {r[2]}')
print(f'\n  Total: {len(ok)} OK | {len(fail)} failed')
