import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

orders = [
    ('SOL1205358', 'SHP27-11655'),
    ('SOL1200450', 'SHP27-06613'),
    ('SOL1202432', 'SHP27-08679'),
    ('SOL1202791', 'SHP27-09090'),
    ('SOL1202422', 'SHP27-08669'),
    ('SOL1197981', 'SHP27-04151'),
    ('SOL1206214', 'SHP27-12514'),
    ('SOL1205979', 'SHP27-12283'),
]

results = []

for sol, so_name in orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} | {so_name} ===')

    r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so = r.json().get('data', {})
    cust = so.get('customer', '')
    shipping_addr = so.get('shipping_address_name', '')
    cust_addr = so.get('customer_address', '')
    taxes_template = so.get('taxes_and_charges', '')
    items = ', '.join([i.get('item_code','') + ' x' + str(int(i.get('qty',1))) for i in so.get('items', [])])
    print(f'  {cust} | {items} | Shipping: {shipping_addr}')

    # Make DN from SO
    r2 = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r2.status_code != 200:
        print(f'  make_delivery_note failed: {r2.status_code}')
        results.append((sol, 'MAKE_DN_FAIL', so_name, '', cust))
        continue

    dn_draft = r2.json().get('message', {})
    dn_draft['shipping_address_name'] = shipping_addr
    dn_draft['customer_address'] = cust_addr or shipping_addr

    # Fix taxes: ensure item_wise_tax_detail is not None
    for tax in dn_draft.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'

    # Remove item_tax_template from items
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)

    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    # Save DN
    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        err = r3.text[:400]
        print(f'  DN save failed: {r3.status_code} {err}')
        results.append((sol, 'DN_SAVE_FAIL', so_name, '', cust))
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
            if 'NegativeStockError' in err:
                results.append((sol, 'NO_STOCK', so_name, dn_name, cust))
            else:
                results.append((sol, 'DN_SUBMIT_FAIL', so_name, dn_name, cust))
            continue
    else:
        err = r4.text[:300]
        print(f'  DN submit failed: {r4.status_code} {err}')
        if 'NegativeStockError' in err:
            results.append((sol, 'NO_STOCK', so_name, dn_name, cust))
        else:
            results.append((sol, 'DN_SUBMIT_FAIL', so_name, dn_name, cust))
        continue

    # Check AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner', 'docstatus'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')
    print(f'  AWB={awb} | {courier}')
    results.append((sol, 'OK', so_name, dn_name, cust, f'{awb} ({courier})'))
    time.sleep(0.5)

print(f'\n\n{"="*80}')
print('SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] != 'OK']
for r in ok:
    print(f'  OK       {r[0]} | {r[4]} | {r[2]} | {r[3]} | {r[5]}')
for r in fail:
    dn_info = r[3] if len(r) > 3 else ''
    cust_info = r[4] if len(r) > 4 else ''
    print(f'  {r[1]:15s} {r[0]} | {cust_info} | {r[2]} | {dn_info}')
print(f'\n  Total: {len(ok)} OK | {len(fail)} failed')
