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

# Group B: PIN mismatch - fix Atlas address from Shopify, then submit draft DN
orders = [
    # (sol, atlas_pin, shopify_pin)
    ('SOL1204747', '440008', '201015'),  # AnuragSingh
    ('SOL1204873', '500084', '411027'),  # Mansoor
    ('SOL1204894', '600073', '605013'),  # Suganya
    ('SOL1204918', '400013', '400028'),  # SuzanaFernandes PPCOD
    ('SOL1205054', '400706', '401303'),  # Dr. Jayshree Patil
]

results = []

for sol, old_pin, expected_pin in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | Fix PIN {old_pin} -> Shopify ===')

    # Get SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','custom_order_type','custom_cod_amount','grand_total',
                                      'shopify_order_id','shipping_address_name','customer','customer_name']),
                'limit_page_length': 1}, timeout=15)
    so_data = r_so.json().get('data', [])
    if not so_data:
        print(f'  SO NOT FOUND')
        results.append((sol, 'FAIL', '', '', 'SO not found'))
        continue

    so = so_data[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    addr_name = so.get('shipping_address_name', '')
    customer = so.get('customer', '')
    atlas_type = so.get('custom_order_type', '') or ''
    cod_amount = float(so.get('custom_cod_amount', 0) or 0)
    grand_total = float(so.get('grand_total', 0) or 0)

    print(f'  SO: {so_name} | {so.get("customer_name","")} | {atlas_type} | COD={cod_amount} | Total={grand_total}')
    print(f'  Current Atlas addr: {addr_name}')

    # Get Shopify shipping address
    if not shopify_oid:
        print(f'  No shopify_order_id!')
        results.append((sol, 'FAIL', so_name, '', 'No shopify_order_id'))
        continue

    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    sh_order = r_sh.json().get('order', {})
    sa = sh_order.get('shipping_address', {})
    sh_pin = str(sa.get('zip', ''))
    sh_addr1 = sa.get('address1', '') or ''
    sh_addr2 = sa.get('address2', '') or ''
    sh_city = sa.get('city', '') or ''
    sh_state = sa.get('province', '') or ''
    sh_name = sa.get('name', '') or ''
    sh_phone = sa.get('phone', '') or ''
    sh_country = sa.get('country_code', 'IN') or 'IN'

    # Clean phone
    phone = sh_phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10:
        phone = phone[-10:]

    print(f'  Shopify addr: {sh_name} | {sh_addr1}, {sh_addr2} | {sh_city} {sh_state} PIN={sh_pin}')
    print(f'  Phone: {phone}')

    # Check serviceability with correct Shopify PIN
    ot = 'PREPAID' if atlas_type not in ('PPCOD', 'COD') else 'COD'
    cv = cod_amount if ot == 'COD' else 0
    payload_svc = [{'pickup_pincode': '501218', 'drop_pincode': sh_pin, 'order_type': ot,
                    'cod_value': cv, 'delivery_type': 'FORWARD', 'item': 'DGS',
                    'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': max(grand_total,1)}]
    r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
        json=payload_svc, headers={'Content-Type': 'application/json'}, timeout=10)
    svc = r_svc.json()
    couriers = []
    if svc.get('meta', {}).get('success') and svc.get('result', [{}])[0].get('preference_array'):
        couriers = [c.get('courier_name','') for c in svc['result'][0]['preference_array']]
        print(f'  Serviceable ({ot}): {", ".join(couriers)}')
    else:
        print(f'  NOT SERVICEABLE at Shopify PIN {sh_pin}!')
        results.append((sol, 'FAIL', so_name, '', f'PIN {sh_pin} not serviceable'))
        continue

    # Step 1: Create new per-order Address with Shopify data
    new_addr_name = f'{customer}-{sol}-Shipping'
    print(f'  Creating address: {new_addr_name}')

    # Map Shopify state to Atlas state
    state_map = {
        'Uttar Pradesh': 'Uttar Pradesh', 'Maharashtra': 'Maharashtra', 'Tamil Nadu': 'Tamil Nadu',
        'Karnataka': 'Karnataka', 'Telangana': 'Telangana', 'Gujarat': 'Gujarat',
        'West Bengal': 'West Bengal', 'Rajasthan': 'Rajasthan', 'Delhi': 'Delhi',
        'Madhya Pradesh': 'Madhya Pradesh', 'Uttarakhand': 'Uttarakhand',
        'Jammu & Kashmir': 'Jammu and Kashmir', 'Jammu and Kashmir': 'Jammu and Kashmir',
        'Andaman and Nicobar Islands': 'Andaman and Nicobar Islands',
        'Andhra Pradesh': 'Andhra Pradesh', 'Punjab': 'Punjab', 'Haryana': 'Haryana',
        'Bihar': 'Bihar', 'Odisha': 'Odisha', 'Kerala': 'Kerala', 'Goa': 'Goa',
        'Jharkhand': 'Jharkhand', 'Assam': 'Assam', 'Chhattisgarh': 'Chhattisgarh',
        'Himachal Pradesh': 'Himachal Pradesh', 'Manipur': 'Manipur',
        'Dadra and Nagar Haveli': 'Dadra and Nagar Haveli and Daman and Diu',
    }
    atlas_state = state_map.get(sh_state, sh_state)

    # Delete existing if any
    requests.delete(f'{BASE}/api/resource/Address/{new_addr_name}', headers=H, timeout=10)
    time.sleep(0.5)

    addr_payload = {
        'name': new_addr_name,
        'address_title': sh_name or customer,
        'address_type': 'Shipping',
        'address_line1': sh_addr1 or 'NA',
        'address_line2': sh_addr2,
        'city': sh_city or 'NA',
        'state': atlas_state,
        'pincode': sh_pin,
        'country': 'India',
        'phone': phone,
        'email_id': sh_order.get('email', '') or '',
        'links': [{'link_doctype': 'Customer', 'link_name': customer}],
    }

    r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_addr.status_code in (200, 201):
        created_addr = r_addr.json().get('data', {}).get('name', new_addr_name)
        print(f'  ✓ Address created: {created_addr}')
    else:
        # Maybe already exists with different name format
        print(f'  Address create: {r_addr.status_code} {r_addr.text[:200]}')
        # Try to find it
        r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
            params={'filters': json.dumps([['name','like',f'%{sol}%']]),
                    'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
        found = r_find.json().get('data', [])
        if found:
            created_addr = found[0]['name']
            print(f'  Using existing: {created_addr}')
        else:
            results.append((sol, 'FAIL', so_name, '', 'Address create failed'))
            continue

    # Step 2: Update SO shipping_address_name via server script
    sn = 'tmp_fixaddr_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order','" + so_name + "','shipping_address_name','" + created_addr + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order','" + so_name + "','customer_address','" + created_addr + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    if msg:
        print(f'  ✓ SO address updated to {created_addr}')

    # Step 3: Find draft DN and delete it (we'll create fresh with correct address)
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 5}, timeout=15)
    draft_dns = r_dn.json().get('data', [])
    for dd in draft_dns:
        print(f'  Deleting draft DN {dd["name"]}...')
        requests.delete(f'{BASE}/api/resource/Delivery Note/{dd["name"]}', headers=H, timeout=15)
        time.sleep(0.5)

    # Step 4: Create fresh DN from SO with correct Shopify fields
    r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so_full.json().get('data', {})

    dn_items = []
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic:
            continue  # skip ghost
        dn_items.append({
            'item_code': ic,
            'qty': it.get('qty', 0),
            'rate': it.get('rate', 0),
            'against_sales_order': so_name,
            'so_detail': it.get('name', ''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
        })

    if not dn_items:
        print(f'  No valid items for DN!')
        results.append((sol, 'FAIL', so_name, '', 'No valid items'))
        continue

    dn_payload = {
        'customer': customer,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': created_addr,
        'customer_address': created_addr,
        'custom_order_type': atlas_type,
        'items': dn_items,
        'taxes_and_charges': so_full.get('taxes_and_charges', ''),
    }

    # Set COD amount if PPCOD
    if atlas_type == 'PPCOD':
        dn_payload['custom_cod_amount'] = cod_amount

    print(f'  Creating DN with correct address...')
    r_dn_create = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)

    if r_dn_create.status_code not in (200, 201):
        print(f'  DN create FAIL: {r_dn_create.status_code} {r_dn_create.text[:300]}')
        results.append((sol, 'FAIL', so_name, '', f'DN create failed: {r_dn_create.status_code}'))
        continue

    new_dn = r_dn_create.json().get('data', {}).get('name', '')
    print(f'  ✓ DN created: {new_dn}')

    # Step 5: Submit DN (triggers Clickpost AWB + Shopify fulfillment)
    print(f'  Submitting DN {new_dn}...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
        headers=H, json={'docstatus': 1}, timeout=60)

    if r_sub.status_code == 200:
        dn_data = r_sub.json().get('data', {})
        awb = dn_data.get('awb_number', '') or ''
        courier = dn_data.get('courier_partner', '') or ''
        print(f'  ✓ DN submitted | AWB={awb} | Courier={courier}')

        if not awb:
            # Check after a moment - sometimes AWB is set async
            time.sleep(3)
            r_check = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                headers=H, params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            dn_check = r_check.json().get('data', {})
            awb = dn_check.get('awb_number', '') or ''
            courier = dn_check.get('courier_partner', '') or ''
            if awb:
                print(f'  ✓ AWB (delayed): {awb} via {courier}')
            else:
                print(f'  ⚠ No AWB after submit - may need manual Clickpost')

        results.append((sol, 'OK', new_dn, awb, courier))
    else:
        err = r_sub.text[:300]
        print(f'  DN submit FAIL: {r_sub.status_code} {err}')
        results.append((sol, 'FAIL', new_dn, '', f'Submit failed: {r_sub.status_code}'))

    time.sleep(1)

print(f'\n\n{"="*80}')
print('GROUP B SUMMARY')
print(f'{"="*80}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]}')
    else:
        print(f'  ✗ {r[0]}: {r[4]}')
