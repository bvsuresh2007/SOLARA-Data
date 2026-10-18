import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Group A: Ready to ship
group_a = [
    # (sol, so_name, existing_draft_dn or None)
    ('SOL1204001', 'SHP27-10306', 'SHPDN27-11365'),
    ('SOL1203988', 'SHP27-10293', 'SHPDN27-11375'),
    ('SOL1203978', 'SHP27-10283', 'SHPDN27-11383'),
    ('SOL1203961', 'SHP27-10266', 'SHPDN27-11394'),
    ('SOL1203749', 'SHP27-10054', 'SHPDN27-11539'),
    ('SOL1203815', 'SHP27-10122', 'SHPDN27-11620'),
    ('SOL1203882', 'SHP27-10792', None),  # No DN yet
]

results = []

for sol, so_name, draft_dn in group_a:
    print(f'\n{"="*70}')
    print(f'=== {sol} | SO={so_name} ===')

    # Step 1: Check if draft DN has shopify fields
    if draft_dn:
        r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{draft_dn}', headers=H,
            params={'fields': json.dumps(['docstatus','shopify_order_id','shopify_order_number','shipping_address_name'])}, timeout=15)
        dn_d = r_dn.json().get('data', {})
        dn_oid = dn_d.get('shopify_order_id', '')
        dn_son = dn_d.get('shopify_order_number', '')
        dn_ship = dn_d.get('shipping_address_name', '')
        ds = dn_d.get('docstatus', 0)

        if ds != 0:
            print(f'  DN {draft_dn} is not draft (ds={ds}), skipping')
            results.append((sol, 'SKIP_DS', draft_dn))
            continue

        print(f'  Draft DN: {draft_dn} | OID={dn_oid} | SON={dn_son} | Ship={dn_ship}')

        # If missing shopify fields, delete draft and recreate
        if not dn_oid or not dn_son:
            print(f'  Missing Shopify fields, deleting draft and recreating...')
            requests.delete(f'{BASE}/api/resource/Delivery Note/{draft_dn}', headers=H, timeout=15)
            time.sleep(1)
            draft_dn = None

    # Step 2: Create DN if needed
    if not draft_dn:
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
            params={'fields': json.dumps(['shopify_order_id','shopify_order_number','shipping_address_name','customer_address'])}, timeout=15)
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

        draft_dn = r_ins.json().get('data', {}).get('name', '')
        print(f'  DN created: {draft_dn}')

    # Step 3: Submit DN
    print(f'  Submitting {draft_dn}...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{draft_dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(4)

    # Step 4: Check result
    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{draft_dn}', headers=H,
        params={'fields': json.dumps(['docstatus','awb_number','courier_partner','shopify_fulfillment_id'])}, timeout=15)
    vd = r_v.json().get('data', {})
    ds = vd.get('docstatus', 0)
    awb = vd.get('awb_number', '') or ''
    cp = vd.get('courier_partner', '') or ''
    ful = vd.get('shopify_fulfillment_id', '') or ''

    if ds == 1 and awb:
        print(f'  OK: AWB={awb} | {cp} | Fulfillment={ful}')
        results.append((sol, 'OK', draft_dn, awb, cp))
    elif ds == 1:
        print(f'  SUBMITTED but NO AWB')
        # Check error
        try:
            r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                params={'filters': json.dumps([['error','like','%'+draft_dn+'%']]),
                        'fields': json.dumps(['error']),
                        'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
            errs = r_err.json().get('data', [])
            if errs:
                err = str(errs[0].get('error',''))
                for line in err.split('\n'):
                    ll = line.lower()
                    if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative']):
                        print(f'  ERR: {line.strip()[:180]}')
                        break
        except:
            pass
        results.append((sol, 'NO_AWB', draft_dn))
    else:
        # Submit failed
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
        results.append((sol, 'FAIL_SUBMIT', draft_dn, msg[:80]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP A SUMMARY')
print(f'{"="*70}')
for r in results:
    status = r[1]
    if status == 'OK':
        print(f'  {r[0]}: ✓ {r[2]} AWB={r[3]} {r[4]}')
    elif status == 'NO_AWB':
        print(f'  {r[0]}: ⚠ {r[2]} Submitted but no AWB')
    else:
        print(f'  {r[0]}: ✗ {status} {" ".join(str(x) for x in r[2:])}')
