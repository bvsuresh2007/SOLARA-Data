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

state_map = {
    'Uttar Pradesh': 'Uttar Pradesh', 'Maharashtra': 'Maharashtra', 'Tamil Nadu': 'Tamil Nadu',
    'Karnataka': 'Karnataka', 'Telangana': 'Telangana', 'Gujarat': 'Gujarat',
    'West Bengal': 'West Bengal', 'Rajasthan': 'Rajasthan', 'Delhi': 'Delhi',
    'Puducherry': 'Puducherry', 'Uttarakhand': 'Uttarakhand',
    'Jammu & Kashmir': 'Jammu and Kashmir', 'Jammu and Kashmir': 'Jammu and Kashmir',
    'Andhra Pradesh': 'Andhra Pradesh', 'Punjab': 'Punjab', 'Haryana': 'Haryana',
    'Bihar': 'Bihar', 'Odisha': 'Odisha', 'Kerala': 'Kerala', 'Goa': 'Goa',
    'Dadra and Nagar Haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    'Dadra and Nagar Haveli and Daman and Diu': 'Dadra and Nagar Haveli and Daman and Diu',
}

CUSTOMER = 'Shopify D2C Customer'

results = []
orders_to_create = ['SOL1204809','SOL1204919','SOL1205015','SOL1205022','SOL1205080']

for sol in orders_to_create:
    print(f'\n{"="*70}')
    print(f'=== {sol} ===')

    # Get Shopify order
    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
        headers=SHOP_H, params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
    o = r_sh.json().get('orders', [])[0]
    shopify_oid = str(o['id'])
    sa = o.get('shipping_address', {}) or {}
    fin = o.get('financial_status', '')
    total = float(o.get('total_price', '0'))
    subtotal = float(o.get('subtotal_price', '0'))
    tax_total = float(o.get('total_tax', '0'))

    # Transactions
    r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
    txns = r_txn.json().get('transactions', [])
    captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')

    # Order type
    if fin == 'paid':
        otype = 'Prepaid'
        cod_val = 0
    elif fin == 'partially_paid':
        otype = 'PPCOD'
        cod_val = round(total - captured, 2)
    else:
        otype = 'COD'
        cod_val = total

    # Phone
    phone = str(sa.get('phone', ''))
    phone = phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10:
        phone = phone[-10:]

    sh_state = sa.get('province', '') or ''
    atlas_state = state_map.get(sh_state, sh_state)
    pin = str(sa.get('zip', ''))

    print(f'  {sa.get("name","")} | {sa.get("city","")} {atlas_state} PIN={pin} | Phone={phone}')
    print(f'  {otype} | Total={total} | COD={cod_val} | Captured={captured}')

    # Items
    line_items = o.get('line_items', [])
    for li in line_items:
        print(f'  Item: {li.get("sku","")} x{li.get("quantity",0)} @ {li.get("price","")}')

    # Step 1: Create Address
    addr_name = f'{CUSTOMER}-{sol}-Shipping'
    requests.delete(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=10)
    time.sleep(0.5)

    addr_payload = {
        'name': addr_name,
        'address_title': sa.get('name', '') or CUSTOMER,
        'address_type': 'Shipping',
        'address_line1': sa.get('address1', '') or 'NA',
        'address_line2': sa.get('address2', '') or '',
        'city': sa.get('city', '') or 'NA',
        'state': atlas_state,
        'pincode': pin,
        'country': 'India',
        'phone': phone,
        'email_id': o.get('email', '') or '',
        'links': [{'link_doctype': 'Customer', 'link_name': CUSTOMER}],
    }
    r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_addr.status_code in (200, 201):
        created_addr = r_addr.json().get('data', {}).get('name', addr_name)
        print(f'  ✓ Address: {created_addr}')
    else:
        print(f'  Address fail: {r_addr.status_code} {r_addr.text[:200]}')
        # Try find existing
        r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
            params={'filters': json.dumps([['name','like',f'%{sol}%']]),
                    'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
        found = r_find.json().get('data', [])
        if found:
            created_addr = found[0]['name']
            print(f'  Using existing: {created_addr}')
        else:
            results.append((sol, 'FAIL', '', '', 'Address failed'))
            continue

    # Step 2: Create SO via 2-step server script
    # Build items append lines
    items_lines = ''
    for li in line_items:
        sku = li.get('sku', '')
        qty = li.get('quantity', 1)
        price = float(li.get('price', '0'))
        # Calculate rate without tax (price includes tax for Shopify)
        # Shopify total_tax is 0 for these orders (tax inclusive pricing)
        # Use price / 1.18 for IGST 18%
        rate = round(price / 1.18, 2)
        items_lines += (
            "so.append('items', {"
            "'item_code': '" + sku + "', "
            "'qty': " + str(qty) + ", "
            "'rate': " + str(rate) + ", "
            "'warehouse': 'Main Warehouse - WTBBPL'"
            "})\n"
        )

    sn1 = 'tmp_cso1_' + sol.lower()
    script1 = (
        "so = frappe.new_doc('Sales Order')\n"
        "so.customer = '" + CUSTOMER + "'\n"
        "so.shopify_order_id = '" + shopify_oid + "'\n"
        "so.shopify_order_number = '" + sol + "'\n"
        "so.custom_shopify_order_number = '" + sol + "'\n"
        "so.custom_order_type = '" + otype + "'\n"
        "so.custom_cod_amount = " + str(cod_val) + "\n"
        "so.shipping_address_name = '" + created_addr + "'\n"
        "so.customer_address = '" + created_addr + "'\n"
        "so.delivery_date = '2026-05-09'\n"
        + items_lines +
        "so.flags.ignore_validate = True\n"
        "so.flags.ignore_mandatory = True\n"
        "so.flags.ignore_permissions = True\n"
        "so.insert(ignore_permissions=True)\n"
        "frappe.db.commit()\n"
        "frappe.response['message'] = so.name\n"
    )

    print(f'  Creating SO (step 1)...')
    so_name = run_server_script(sn1, script1)
    if not so_name or so_name == 'None':
        print(f'  ✗ SO create step 1 failed')
        results.append((sol, 'FAIL', '', '', 'SO step1 failed'))
        continue
    print(f'  ✓ SO draft: {so_name}')

    # Step 2: Set taxes, company address, submit
    sn2 = 'tmp_cso2_' + sol.lower()
    script2 = (
        "so = frappe.get_doc('Sales Order', '" + so_name + "')\n"
        "so.company_address = 'WIN THE BUY BOX PVT LTD (Delivery Address)-Shipping'\n"
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

    print(f'  Submitting SO (step 2)...')
    msg2 = run_server_script(sn2, script2)
    if msg2 and msg2.startswith('1'):
        parts = msg2.split('|')
        print(f'  ✓ SO submitted | grand_total={parts[1] if len(parts)>1 else "?"}')
    else:
        print(f'  ✗ SO step 2 result: {msg2}')
        results.append((sol, 'FAIL', so_name, '', f'SO step2: {msg2}'))
        continue

    # Step 3: Set shopify_order_id on SO (in case hook needs it)
    time.sleep(1)

    # Step 4: Create DN
    r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so_full.json().get('data', {})

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
        'shipping_address_name': created_addr,
        'customer_address': created_addr,
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

    # Step 5: Submit DN
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

        # Check Shopify
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
