import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Group B: Ghost SKU fix
# SOL1204715 - Madhukar Kale, 422009 Nashik - ghost child b8l3ej0nr9 -> SOL-AF-MITTEN
# SOL1204541 - GARIMA SAXENA, 110085 Delhi - ghost child 36ie0s173t -> SOL-CI-KD-103-DT-103-FP-102 (2nd item SOL-CKW-WSPA-101 is OK)

ghost_fixes = [
    ('SOL1204715', 'SHP27-11016', 'b8l3ej0nr9', 'SOL-AF-MITTEN'),
    ('SOL1204541', 'SHP27-10844', '36ie0s173t', 'SOL-CI-KD-103-DT-103-FP-102'),
]

results = []

# Step 1: Fix ghost SKUs
print("STEP 1: Fixing ghost SKUs on SOs")
print("=" * 70)
for sol, so_name, child_name, sku in ghost_fixes:
    sn = 'tmp_fix_ghost_' + so_name.replace('-', '_').lower()
    script = (
        "frappe.db.set_value('Sales Order Item','" + child_name + "','item_code','" + sku + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "v = frappe.db.get_value('Sales Order Item','" + child_name + "','item_code')\n"
        "frappe.response['message'] = str(v)\n"
    )
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code == 200:
        time.sleep(1)
        r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
        msg = r2.json().get('message', '')
        print(f'  {sol} ({so_name}) child={child_name}: item_code={msg}')
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
    else:
        print(f'  {sol}: Script create FAIL {r.status_code} {r.text[:200]}')
    time.sleep(0.5)

# Step 2: Create DNs and submit
print(f'\nSTEP 2: Creating and submitting DNs')
print("=" * 70)

orders = [
    ('SOL1204715', 'SHP27-11016'),
    ('SOL1204541', 'SHP27-10844'),
]

for sol, so_name in orders:
    print(f'\n--- {sol} | SO={so_name} ---')

    # Check existing DNs - delete any drafts
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number', '=', sol]]),
                'fields': json.dumps(['name', 'docstatus', 'awb_number']),
                'limit_page_length': 5}, timeout=15)
    dns = r_dn.json().get('data', [])

    for d in dns:
        if d.get('docstatus') == 0:
            print(f'  Deleting draft DN {d["name"]}...')
            requests.delete(f'{BASE}/api/resource/Delivery Note/{d["name"]}', headers=H, timeout=15)
            time.sleep(1)

    # Create fresh DN from SO
    print(f'  Creating DN from SO {so_name}...')
    r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                           headers=H, json={'source_name': so_name}, timeout=30)
    if r_make.status_code != 200:
        print(f'  make_dn FAIL: {r_make.status_code} {r_make.text[:200]}')
        results.append((sol, 'FAIL_MAKE'))
        continue

    dn_doc = r_make.json().get('message', {})

    # Copy shopify fields from SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
        params={'fields': json.dumps(['shopify_order_id', 'shopify_order_number', 'shipping_address_name', 'customer_address'])}, timeout=15)
    so_d = r_so.json().get('data', {})
    dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or ''
    dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
    dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or dn_doc.get('shipping_address_name', '')
    dn_doc['customer_address'] = so_d.get('customer_address') or dn_doc.get('customer_address', '')

    r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_doc, timeout=30)
    if r_ins.status_code != 200:
        print(f'  DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}')
        results.append((sol, 'FAIL_INSERT'))
        continue

    new_dn = r_ins.json().get('data', {}).get('name', '')
    print(f'  DN created: {new_dn}')

    # Submit DN
    print(f'  Submitting {new_dn}...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(4)

    # Check result
    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
        params={'fields': json.dumps(['docstatus', 'awb_number', 'courier_partner', 'shopify_fulfillment_id'])}, timeout=15)
    vd = r_v.json().get('data', {})
    ds = vd.get('docstatus', 0)
    awb = vd.get('awb_number', '') or ''
    cp = vd.get('courier_partner', '') or ''
    ful = vd.get('shopify_fulfillment_id', '') or ''

    if ds == 1 and awb:
        print(f'  OK: AWB={awb} | {cp} | Fulfillment={ful}')
        results.append((sol, 'OK', new_dn, awb, cp))
    elif ds == 1:
        print(f'  SUBMITTED but NO AWB')
        try:
            r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                params={'filters': json.dumps([['error', 'like', '%' + new_dn + '%']]),
                        'fields': json.dumps(['error']),
                        'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
            errs = r_err.json().get('data', [])
            if errs:
                err = str(errs[0].get('error', ''))
                for line in err.split('\n'):
                    ll = line.lower()
                    if any(k in ll for k in ['clickpost', 'serviceable', 'cod', 'pincode', 'error', 'fail', 'stock', 'negative', 'mismatch', 'address', 'phone']):
                        print(f'  ERR: {line.strip()[:180]}')
                        break
        except:
            pass
        results.append((sol, 'NO_AWB', new_dn))
    else:
        msg = ''
        try:
            msgs = r_sub.json().get('_server_messages', '')
            if msgs:
                for p in json.loads(msgs):
                    inner = json.loads(p) if isinstance(p, str) else p
                    m = inner.get('message', str(inner))
                    if 'Item Price' not in m:
                        msg = m[:150]
                        break
        except:
            msg = str(r_sub.status_code)
        print(f'  FAIL ds={ds}: {msg}')
        results.append((sol, 'FAIL_SUBMIT', new_dn, msg[:80]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP B SUMMARY')
print(f'{"="*70}')
for r in results:
    status = r[1]
    if status == 'OK':
        print(f'  {r[0]}: OK {r[2]} AWB={r[3]} {r[4]}')
    elif status == 'NO_AWB':
        print(f'  {r[0]}: NO_AWB {r[2]}')
    else:
        print(f'  {r[0]}: {status} {" ".join(str(x) for x in r[2:])}')
