import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# 3 orders with SO but no DN
orders = [
    ('SOL1202946', 'SHP27-09241'),  # SOL-CI-KD-101x1
    ('SOL1202977', 'SHP27-09272'),  # SOL-LIT-101x1, ?x1, SOL-CKW-WSPA-101x1 (ghost SKU)
    ('SOL1203097', 'SHP27-09408'),  # SOL-INS-WB-208x1, SOL-MBL-COM-IVR-P13x1, ?x1 (ghost SKU)
]

results = []
for sol, so in orders:
    print(f"\n=== {sol} ({so}) ===")

    # Check SO details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so}', headers=H, timeout=30)
    so_d = r_so.json().get('data', {})
    print(f"  Customer: {so_d.get('customer_name','')}")
    print(f"  Status: {so_d.get('status','')} ds={so_d.get('docstatus',0)}")

    items = so_d.get('items', [])
    print(f"  Items:")
    has_ghost = False
    for it in items:
        ic = it.get('item_code', '')
        qty = int(it.get('qty', 0))
        dlvd = int(it.get('delivered_qty', 0))
        print(f"    {ic or '(empty)'} qty={qty} delivered={dlvd}")
        if not ic:
            has_ghost = True

    if has_ghost:
        print(f"  ** HAS GHOST/EMPTY ITEM CODE — needs manual fix first **")
        results.append((sol, so, 'GHOST_SKU', '', ''))
        continue

    if so_d.get('docstatus', 0) != 1:
        print(f"  ** SO not submitted **")
        results.append((sol, so, 'NOT_SUBMITTED', '', ''))
        continue

    # Create DN from SO
    r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                           headers=H, json={'source_name': so}, timeout=30)
    if r_make.status_code != 200:
        print(f"  make_delivery_note FAIL: {r_make.status_code} {r_make.text[:200]}")
        results.append((sol, so, 'FAIL_MAKE', '', ''))
        continue

    new_dn_doc = r_make.json().get('message', {})

    # Copy shopify fields from SO
    new_dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or ''
    new_dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
    new_dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or new_dn_doc.get('shipping_address_name', '')
    new_dn_doc['customer_address'] = so_d.get('customer_address') or new_dn_doc.get('customer_address', '')

    # Insert
    r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=new_dn_doc, timeout=30)
    if r_ins.status_code != 200:
        print(f"  DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}")
        results.append((sol, so, 'FAIL_INSERT', '', ''))
        continue

    new_dn = r_ins.json().get('data', {}).get('name', '')
    print(f"  New DN: {new_dn}")

    # Submit
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(4)

    # Verify
    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                       params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
    vd = r_v.json().get('data', {})
    awb = vd.get('awb_number') or ''
    cp = vd.get('courier_partner') or ''
    ds = vd.get('docstatus', 0)

    if ds == 1 and awb:
        print(f"  OK: AWB={awb} {cp}")
        results.append((sol, so, 'OK', new_dn, awb))
    elif ds == 1:
        print(f"  SUBMITTED but no AWB")
        results.append((sol, so, 'NO_AWB', new_dn, ''))
    else:
        msg = ''
        try:
            msgs = r_sub.json().get('_server_messages', '')
            if msgs:
                for p in json.loads(msgs):
                    inner = json.loads(p) if isinstance(p, str) else p
                    m = inner.get('message', str(inner))
                    if 'Item Price' not in m:
                        msg = m[:120]
                        break
        except:
            msg = str(r_sub.status_code)
        print(f"  SUBMIT FAIL ds={ds}: {msg[:100]}")
        results.append((sol, so, 'FAIL_SUBMIT', new_dn, msg[:80]))

    time.sleep(1)

print(f"\n{'='*80}")
print(f"SUMMARY")
for r in results:
    print(f"  {r[0]} {r[1]} -> {r[2]} {r[3]} {r[4]}")
