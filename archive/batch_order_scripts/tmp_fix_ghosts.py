import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

fixes = [
    ('SHP27-09272', 'SOL-CI-DT-103-FP-103', "CrownStone Cast Iron Fry Pan - 12 ' Inch / Frypan 12"),
    ('SHP27-09408', 'SOL-INS-WB-401-SLB-201', 'Kids Lunch Box - Unicorn / Lunch Box + Insulated Water Bottle'),
]

for so, correct_sku, item_name_match in fixes:
    print(f"\n=== Fixing {so} -> {correct_sku} ===")

    # First verify the SKU exists in ERPNext
    r_item = requests.get(f'{BASE}/api/resource/Item/{correct_sku}', headers=H, timeout=15)
    if r_item.status_code != 200:
        print(f"  SKU {correct_sku} NOT FOUND in ERPNext — needs to be created first")
        continue

    item_data = r_item.json().get('data', {})
    if isinstance(item_data, list):
        item_data = item_data[0] if item_data else {}
    print(f"  SKU exists: {item_data.get('item_name','')} | is_stock={item_data.get('is_stock_item',1)}")

    # Find the ghost SO item row
    sn = 'tmp_fix_' + so.replace('-', '_').lower()
    script = """
so = '""" + so + """'
sku = '""" + correct_sku + """'

rows = frappe.db.sql(
    "SELECT name, item_code, item_name FROM `tabSales Order Item` "
    "WHERE parent = %s AND docstatus = 1 AND (item_code = '' OR item_code IS NULL)",
    (so,), as_dict=True
)

if not rows:
    frappe.response["message"] = "NO_GHOST_ROW"
else:
    child_name = rows[0]['name']
    frappe.db.set_value('Sales Order Item', child_name, 'item_code', sku, update_modified=False)
    frappe.db.set_value('Sales Order Item', child_name, 'item_name', sku, update_modified=False)
    frappe.db.commit()

    chk = frappe.db.sql("SELECT item_code, item_name FROM `tabSales Order Item` WHERE name = %s", (child_name,), as_dict=True)
    frappe.response["message"] = "FIXED " + str(chk[0]['item_code']) + " | " + str(chk[0]['item_name']) if chk else "VERIFY_FAIL"
"""

    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code == 200:
        time.sleep(1)
        r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
        print(f"  Result: {r2.json().get('message', '')}")
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
    else:
        print(f"  Script create fail: {r.status_code} {r.text[:200]}")

    time.sleep(0.5)

# Now create DNs for both
print(f"\n\n=== CREATING DNs ===")
orders = [
    ('SOL1202977', 'SHP27-09272'),
    ('SOL1203097', 'SHP27-09408'),
]

for sol, so in orders:
    print(f"\n--- {sol} ({so}) ---")

    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so}', headers=H, timeout=30)
    so_d = r_so.json().get('data', {})

    # Verify no more ghost items
    has_ghost = False
    for it in so_d.get('items', []):
        if not it.get('item_code', ''):
            has_ghost = True
            print(f"  Still has ghost item: {it.get('item_name','')}")

    if has_ghost:
        print(f"  SKIP — ghost not fixed")
        continue

    # Create DN
    r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                           headers=H, json={'source_name': so}, timeout=30)
    if r_make.status_code != 200:
        print(f"  make_delivery_note FAIL: {r_make.status_code} {r_make.text[:200]}")
        continue

    new_dn_doc = r_make.json().get('message', {})
    new_dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or ''
    new_dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
    new_dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or new_dn_doc.get('shipping_address_name', '')
    new_dn_doc['customer_address'] = so_d.get('customer_address') or new_dn_doc.get('customer_address', '')

    r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=new_dn_doc, timeout=30)
    if r_ins.status_code != 200:
        print(f"  DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}")
        continue

    new_dn = r_ins.json().get('data', {}).get('name', '')
    print(f"  New DN: {new_dn}")

    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                         headers=H, json={'docstatus': 1}, timeout=60)
    time.sleep(4)

    r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                       params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
    vd = r_v.json().get('data', {})
    awb = vd.get('awb_number') or ''
    cp = vd.get('courier_partner') or ''
    ds = vd.get('docstatus', 0)

    if ds == 1 and awb:
        print(f"  OK: AWB={awb} {cp}")
    elif ds == 1:
        print(f"  SUBMITTED no AWB — check error log")
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
        print(f"  FAIL ds={ds}: {msg[:100]}")

    time.sleep(1)
