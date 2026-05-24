import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'    Script create FAIL: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(3)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'    Script error: {exc[:300]}')
        return None
    return msg

# Ghost SKU fixes
ghosts = [
    ('SOL1204795', 'a49i51ruvk', 'SOL-CI-DT-103-FP-103', 'CrownStone Cast Iron Fry Pan 12 Inch + Tawa 12 Inch'),
    ('SOL1204921', '9666jb7jg8', 'SOL-CI-DT-103-FP-103', 'CrownStone Cast Iron Fry Pan 12 Inch + Tawa 12 Inch'),
    ('SOL1204933', '9u9s1bnaas', 'SOL-INS-WB-401-SLB-201', 'Kids Lunch Box Unicorn + Insulated Water Bottle'),
]

results = []

for sol, ghost_child, correct_sku, item_name_str in ghosts:
    print(f'\n{"="*70}')
    print(f'=== {sol} | Fix ghost {ghost_child} -> {correct_sku} ===')

    # Step 1: Fix ghost SKU on SO via server script
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','shopify_order_id','customer','customer_name','shipping_address_name',
                                      'customer_address','custom_order_type','custom_cod_amount','grand_total',
                                      'taxes_and_charges']),
                'limit_page_length': 1}, timeout=15)
    so = r_so.json().get('data', [{}])[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    customer = so.get('customer', '')
    atlas_type = so.get('custom_order_type', '') or ''
    cod_amount = float(so.get('custom_cod_amount', 0) or 0)

    print(f'  SO: {so_name} | {so.get("customer_name","")}')

    # Get item details from Atlas for the correct SKU
    r_item = requests.get(f'{BASE}/api/resource/Item/{correct_sku}', headers=H, timeout=10)
    item_data = r_item.json().get('data', {})
    item_name_atlas = item_data.get('item_name', correct_sku)
    uom = item_data.get('stock_uom', 'Nos')

    sn = 'tmp_ghost_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','item_code','" + correct_sku + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','item_name','" + item_name_atlas.replace("'", "\\'") + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','description','" + item_name_atlas.replace("'", "\\'") + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','uom','" + uom + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','stock_uom','" + uom + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','warehouse','Main Warehouse - WTBBPL',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='fixed'"
    )
    msg = run_server_script(sn, script)
    if msg:
        print(f'  ✓ Ghost fixed: {ghost_child} -> {correct_sku}')
    else:
        print(f'  ✗ Ghost fix failed')
        results.append((sol, 'FAIL', '', '', 'Ghost fix failed'))
        continue

    # Step 2: Delete any existing draft DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 10}, timeout=15)
    for dd in r_dn.json().get('data', []):
        print(f'  Deleting draft DN {dd["name"]}...')
        requests.delete(f'{BASE}/api/resource/Delivery Note/{dd["name"]}', headers=H, timeout=15)
        time.sleep(0.5)

    # Step 3: Re-read SO items (now fixed)
    r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so_full.json().get('data', {})

    dn_items = []
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic:
            print(f'  ⚠ Still ghost: child={it.get("name","")}')
            continue
        dn_items.append({
            'item_code': ic,
            'qty': it.get('qty', 0),
            'rate': it.get('rate', 0),
            'against_sales_order': so_name,
            'so_detail': it.get('name', ''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
        })

    if not dn_items:
        print(f'  No valid items!')
        results.append((sol, 'FAIL', '', '', 'No valid items'))
        continue

    print(f'  Items for DN: {", ".join([f"{i["item_code"]} x{int(i["qty"])}" for i in dn_items])}')

    # Step 4: Create DN
    dn_payload = {
        'customer': customer,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': so.get('shipping_address_name', ''),
        'customer_address': so.get('customer_address', '') or so.get('shipping_address_name', ''),
        'custom_order_type': atlas_type,
        'items': dn_items,
        'taxes_and_charges': so.get('taxes_and_charges', ''),
    }
    if atlas_type == 'PPCOD':
        dn_payload['custom_cod_amount'] = cod_amount

    print(f'  Creating DN...')
    r_dn_create = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)

    if r_dn_create.status_code not in (200, 201):
        print(f'  DN create FAIL: {r_dn_create.status_code} {r_dn_create.text[:300]}')
        results.append((sol, 'FAIL', '', '', f'DN create failed'))
        continue

    new_dn = r_dn_create.json().get('data', {}).get('name', '')
    print(f'  ✓ DN created: {new_dn}')

    # Step 5: Submit DN
    print(f'  Submitting DN {new_dn}...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
        headers=H, json={'docstatus': 1}, timeout=60)

    if r_sub.status_code == 200:
        dn_data = r_sub.json().get('data', {})
        awb = dn_data.get('awb_number', '') or ''
        courier = dn_data.get('courier_partner', '') or ''
        print(f'  ✓ Submitted | AWB={awb} | Courier={courier}')

        if not awb:
            time.sleep(3)
            r_check = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            d2 = r_check.json().get('data', {})
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
            if awb:
                print(f'  ✓ AWB (delayed): {awb} via {courier}')
            else:
                print(f'  ⚠ No AWB after submit')

        # Verify Shopify
        if shopify_oid and awb:
            time.sleep(1)
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh = r_ord.json().get('order', {})
            print(f'  Shopify: fin={sh.get("financial_status","")} | fulfillment={sh.get("fulfillment_status","")}')

        results.append((sol, 'OK', new_dn, awb, courier))
    else:
        err = r_sub.text[:300]
        print(f'  ✗ Submit FAIL: {r_sub.status_code} {err}')
        results.append((sol, 'FAIL', new_dn, '', err[:100]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP D SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]}')
    else:
        print(f'  ✗ {r[0]}: {r[4]}')
