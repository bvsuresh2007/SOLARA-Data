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
    'Puducherry': 'Puducherry', 'Uttarakhand': 'Uttarakhand', 'Sikkim': 'Sikkim',
    'Manipur': 'Manipur', 'Meghalaya': 'Meghalaya', 'Mizoram': 'Mizoram',
    'Nagaland': 'Nagaland', 'Arunachal Pradesh': 'Arunachal Pradesh',
    'Andhra Pradesh': 'Andhra Pradesh', 'Punjab': 'Punjab', 'Haryana': 'Haryana',
}

# Orders to fix: PIN mismatch + submitted DN no AWB
# Need to: fix address, cancel old DN, create new DN, get AWB
# Also fix PPCOD COD=0 on SOL1203024
orders = [
    ('SOL1202999', 'SHP27-09294', 'SHPDN27-10671', '7055715827944', 'Prepaid', 0, 2549.0, 'Gokwik UPI'),
    ('SOL1203024', 'SHP27-09319', 'SHPDN27-10871', '7055767011560', 'PPCOD', 6749.1, 7499.0, 'Gokwik PPCOD'),
    ('SOL1202041', 'SHP27-08273', 'SHPDN27-09921', '7050988454120', 'Prepaid', 0, 1249.0, 'Gokwik UPI'),
    ('SOL1203970', 'SHP27-10275', 'SHPDN27-11388', '7060163100904', 'Prepaid', 0, 7649.0, 'Gokwik Snapmint'),
]

results = []

for sol, so_name, old_dn, shopify_oid, otype, cod_val, total, payment_method in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} | {payment_method} | {otype} ===')

    # Get Shopify shipping address (source of truth)
    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    sh_order = r_sh.json().get('order', {})
    sa = sh_order.get('shipping_address', {}) or {}
    sh_pin = str(sa.get('zip', ''))
    sh_addr1 = sa.get('address1', '') or ''
    sh_addr2 = sa.get('address2', '') or ''
    sh_city = sa.get('city', '') or ''
    sh_state = sa.get('province', '') or ''
    sh_name = sa.get('name', '') or ''
    sh_phone = sa.get('phone', '') or ''

    phone = sh_phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10:
        phone = phone[-10:]
    atlas_state = state_map.get(sh_state, sh_state)

    print(f'  Shopify: {sh_name} | {sh_city} {atlas_state} PIN={sh_pin} | Phone={phone}')

    # Get SO customer
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so.json().get('data', {})
    customer = so_full.get('customer', '')

    # Fix PPCOD COD amount if needed (SOL1203024)
    if otype == 'PPCOD' and cod_val > 0:
        atlas_cod = float(so_full.get('custom_cod_amount', 0) or 0)
        if atlas_cod == 0:
            print(f'  Fixing PPCOD COD amount: 0 -> {cod_val}')
            sn = 'tmp_fixcod_' + sol.lower()
            script = (
                "frappe.db.set_value('Sales Order','" + so_name + "','custom_cod_amount'," + str(cod_val) + ",update_modified=False)\n"
                "frappe.db.set_value('Sales Order','" + so_name + "','custom_order_type','PPCOD',update_modified=False)\n"
                "frappe.db.commit()\n"
                "frappe.response['message']='ok'"
            )
            msg = run_server_script(sn, script)
            if msg:
                print(f'  ✓ COD amount fixed')

    # Step 1: Create new Address from Shopify
    addr_name = f'{customer}-{sol}-Shipping'
    requests.delete(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=10)
    time.sleep(0.5)

    addr_payload = {
        'name': addr_name,
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
        created_addr = r_addr.json().get('data', {}).get('name', addr_name)
        print(f'  ✓ Address: {created_addr}')
    else:
        # Find existing
        r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
            params={'filters': json.dumps([['name','like',f'%{sol}%Shipping%']]),
                    'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
        found = r_find.json().get('data', [])
        if found:
            created_addr = found[0]['name']
            # Update it with correct Shopify data
            requests.put(f'{BASE}/api/resource/Address/{created_addr}', headers=H, json={
                'address_line1': sh_addr1 or 'NA', 'address_line2': sh_addr2,
                'city': sh_city or 'NA', 'state': atlas_state, 'pincode': sh_pin, 'phone': phone
            }, timeout=15)
            print(f'  ✓ Updated existing: {created_addr}')
        else:
            print(f'  ✗ Address failed: {r_addr.status_code} {r_addr.text[:200]}')
            results.append((sol, 'FAIL', '', '', 'Address failed'))
            continue

    # Step 2: Update SO shipping_address
    sn = 'tmp_fixaddr_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order','" + so_name + "','shipping_address_name','" + created_addr + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order','" + so_name + "','customer_address','" + created_addr + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    if msg:
        print(f'  ✓ SO address updated')

    # Step 3: Cancel old submitted DN
    print(f'  Cancelling old DN {old_dn}...')
    sn = 'tmp_cdn_' + old_dn.replace('-','_').lower()
    script = (
        "doc = frappe.get_doc('Delivery Note', '" + old_dn + "')\n"
        "doc.flags.ignore_validate = True\n"
        "doc.cancel()\n"
        "frappe.db.commit()\n"
        "frappe.response['message'] = 'cancelled'\n"
    )
    msg = run_server_script(sn, script)
    print(f'  DN cancel: {msg}')

    # Step 4: Re-read SO items
    time.sleep(1)
    r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full2 = r_so2.json().get('data', {})

    dn_items = []
    for it in so_full2.get('items', []):
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

    # Step 5: Create new DN with correct address + Shopify fields
    dn_payload = {
        'customer': customer,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': created_addr,
        'customer_address': created_addr,
        'custom_order_type': otype,
        'items': dn_items,
        'taxes_and_charges': so_full2.get('taxes_and_charges', ''),
    }
    if otype == 'PPCOD':
        dn_payload['custom_cod_amount'] = cod_val

    print(f'  Creating new DN...')
    r_dn = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn.status_code not in (200, 201):
        print(f'  DN create FAIL: {r_dn.status_code} {r_dn.text[:300]}')
        results.append((sol, 'FAIL', '', '', 'DN create failed'))
        continue

    new_dn = r_dn.json().get('data', {}).get('name', '')
    print(f'  ✓ DN: {new_dn}')

    # Step 6: Submit DN
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

        # Verify Shopify fulfillment + payment
        time.sleep(1)
        r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh = r_ord.json().get('order', {})
        gw = ', '.join(sh.get('payment_gateway_names', []))
        print(f'  Shopify: fin={sh.get("financial_status","")} | fulfillment={sh.get("fulfillment_status","")} | gw={gw}')

        # Verify Atlas SO has correct order_type and COD
        r_so3 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
            params={'fields': json.dumps(['custom_order_type','custom_cod_amount'])}, timeout=15)
        so3 = r_so3.json().get('data', {})
        print(f'  Atlas SO: type={so3.get("custom_order_type","")} | COD={so3.get("custom_cod_amount",0)}')

        results.append((sol, 'OK', new_dn, awb, courier, payment_method))
    else:
        err = r_sub.text[:300]
        print(f'  ✗ Submit FAIL: {r_sub.status_code} {err}')
        results.append((sol, 'FAIL', new_dn, '', err[:100], payment_method))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('FIX SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]} | Payment={r[5]}')
    else:
        print(f'  ✗ {r[0]}: {r[4] if len(r)>4 else ""}')
