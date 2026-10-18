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

CUSTOMER = 'Shopify D2C Customer'
COMPANY_ADDR = 'Win The Buy Box Private Limited-Billing'

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

# Draft SOs already created, just need step 2 (taxes + submit) + DN creation
draft_sos = [
    ('SOL1204809', 'SHP27-11605', '7070923292904', 'PPCOD', 7649.1),
    ('SOL1204919', 'SHP27-11606', '7071139528936', 'PPCOD', 7199.1),
    ('SOL1205015', 'SHP27-11607', '7073082343656', 'PPCOD', 2915.19),
    ('SOL1205022', 'SHP27-11608', '7073106985192', 'PPCOD', 2915.19),
    ('SOL1205080', 'SHP27-11609', '7073684291816', 'Prepaid', 0),
]

results = []

for sol, so_name, shopify_oid, otype, cod_val in draft_sos:
    print(f'\n{"="*70}')
    print(f'=== {sol} | SO={so_name} ===')

    # Step 2: Set taxes + submit
    sn2 = 'tmp_cso2_' + sol.lower()
    script2 = (
        "so = frappe.get_doc('Sales Order', '" + so_name + "')\n"
        "so.company_address = '" + COMPANY_ADDR + "'\n"
        "so.gst_category = 'Unregistered'\n"
        "so.taxes_and_charges = 'Output GST Out-state - WTBBPL'\n"
        "so.run_method('set_missing_values')\n"
        "so.run_method('calculate_taxes_and_totals')\n"
        "so.flags.ignore_validate = True\n"
        "so.flags.ignore_mandatory = True\n"
        "so.flags.ignore_permissions = True\n"
        "so.save(ignore_permissions=True)\n"
        "so.submit()\n"
        "frappe.db.commit()\n"
        "frappe.response['message'] = str(so.docstatus) + '|' + str(so.grand_total)\n"
    )
    print(f'  Submitting SO...')
    msg2 = run_server_script(sn2, script2)
    if not msg2 or not msg2.startswith('1'):
        print(f'  ✗ SO submit failed: {msg2}')
        results.append((sol, 'FAIL', so_name, '', f'SO submit: {msg2}'))
        continue

    parts = msg2.split('|')
    grand_total = float(parts[1]) if len(parts) > 1 else 0
    print(f'  ✓ SO submitted | grand_total={grand_total}')

    # Get SO shipping address
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so.json().get('data', {})
    ship_addr = so_full.get('shipping_address_name', '')
    cust_addr = so_full.get('customer_address', '') or ship_addr

    # Create DN
    dn_items = []
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic:
            continue
        dn_items.append({
            'item_code': ic,
            'qty': it.get('qty', 0),
            'rate': it.get('rate', 0),
            'against_sales_order': so_name,
            'so_detail': it.get('name', ''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
        })

    dn_payload = {
        'customer': CUSTOMER,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': ship_addr,
        'customer_address': cust_addr,
        'custom_order_type': otype,
        'items': dn_items,
        'taxes_and_charges': so_full.get('taxes_and_charges', ''),
    }
    if otype == 'PPCOD':
        dn_payload['custom_cod_amount'] = cod_val

    print(f'  Creating DN...')
    r_dn = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn.status_code not in (200, 201):
        print(f'  DN create FAIL: {r_dn.status_code} {r_dn.text[:300]}')
        results.append((sol, 'FAIL', so_name, '', 'DN create failed'))
        continue

    new_dn = r_dn.json().get('data', {}).get('name', '')
    print(f'  ✓ DN: {new_dn}')

    # Submit DN
    print(f'  Submitting DN...')
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
                print(f'  ⚠ No AWB')

        # Shopify check
        time.sleep(1)
        r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh = r_ord.json().get('order', {})
        print(f'  Shopify: fulfillment={sh.get("fulfillment_status","")}')

        results.append((sol, 'OK', new_dn, awb, courier))
    else:
        err = r_sub.text[:300]
        print(f'  ✗ Submit FAIL: {r_sub.status_code} {err}')
        results.append((sol, 'FAIL', new_dn, '', err[:100]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP E SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]}')
    else:
        print(f'  ✗ {r[0]}: {r[4]}')
