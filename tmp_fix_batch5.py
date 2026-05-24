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
    'Haryana': 'Haryana', 'Kerala': 'Kerala', 'Andhra Pradesh': 'Andhra Pradesh',
    'Punjab': 'Punjab', 'Manipur': 'Manipur', 'Sikkim': 'Sikkim',
}

results = []

# ============================================================
# GROUP A: PIN Mismatch - fix address, delete draft DN, create new, submit
# ============================================================
pin_mismatch_orders = ['SOL1205474','SOL1205370','SOL1205304','SOL1205278','SOL1205201','SOL1205152']

for sol in pin_mismatch_orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} | PIN MISMATCH FIX ===')

    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','shopify_order_id','customer','customer_name','shipping_address_name',
                                      'custom_order_type','custom_cod_amount','grand_total','taxes_and_charges']),
                'limit_page_length': 1}, timeout=15)
    so = r_so.json().get('data', [{}])[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    customer = so.get('customer', '')
    otype = so.get('custom_order_type', '') or 'Prepaid'

    # Get Shopify shipping address
    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    sh_order = r_sh.json().get('order', {})
    sa = sh_order.get('shipping_address', {}) or {}
    sh_pin = str(sa.get('zip', ''))
    sh_state = sa.get('province', '') or ''
    atlas_state = state_map.get(sh_state, sh_state)
    phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10: phone = phone[-10:]

    print(f'  {sa.get("name","")} | {sa.get("city","")} {atlas_state} PIN={sh_pin}')

    # Create address
    addr_name = f'{customer}-{sol}-Shipping'
    requests.delete(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=10)
    time.sleep(0.5)
    addr_payload = {
        'name': addr_name, 'address_title': sa.get('name', '') or customer,
        'address_type': 'Shipping', 'address_line1': sa.get('address1', '') or 'NA',
        'address_line2': sa.get('address2', '') or '', 'city': sa.get('city', '') or 'NA',
        'state': atlas_state, 'pincode': sh_pin, 'country': 'India', 'phone': phone,
        'email_id': sh_order.get('email', '') or '',
        'links': [{'link_doctype': 'Customer', 'link_name': customer}],
    }
    r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_addr.status_code in (200, 201):
        created_addr = r_addr.json().get('data', {}).get('name', addr_name)
    else:
        r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
            params={'filters': json.dumps([['name','like',f'%{sol}%']]),
                    'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
        found = r_find.json().get('data', [])
        if found:
            created_addr = found[0]['name']
            requests.put(f'{BASE}/api/resource/Address/{created_addr}', headers=H, json={
                'address_line1': sa.get('address1','') or 'NA', 'address_line2': sa.get('address2','') or '',
                'city': sa.get('city','') or 'NA', 'state': atlas_state, 'pincode': sh_pin, 'phone': phone
            }, timeout=15)
        else:
            print(f'  ✗ Address failed')
            results.append((sol, 'FAIL', '', '', 'Address failed'))
            continue
    print(f'  ✓ Address: {created_addr}')

    # Update SO address
    sn = 'tmp_fixaddr_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order','" + so_name + "','shipping_address_name','" + created_addr + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order','" + so_name + "','customer_address','" + created_addr + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    run_server_script(sn, script)

    # Delete draft DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']), 'limit_page_length': 10}, timeout=15)
    for dd in r_dn.json().get('data', []):
        requests.delete(f'{BASE}/api/resource/Delivery Note/{dd["name"]}', headers=H, timeout=15)
        time.sleep(0.5)

    # Create fresh DN
    r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so2.json().get('data', {})
    dn_items = []
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic: continue
        dn_items.append({'item_code': ic, 'qty': it.get('qty',0), 'rate': it.get('rate',0),
            'against_sales_order': so_name, 'so_detail': it.get('name',''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL')})

    dn_payload = {
        'customer': customer, 'shopify_order_id': shopify_oid, 'shopify_order_number': sol,
        'custom_shopify_order_number': sol, 'shipping_address_name': created_addr,
        'customer_address': created_addr, 'custom_order_type': otype,
        'items': dn_items, 'taxes_and_charges': so_full.get('taxes_and_charges', ''),
    }
    r_dn_c = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn_c.status_code not in (200, 201):
        print(f'  ✗ DN create FAIL: {r_dn_c.status_code} {r_dn_c.text[:200]}')
        results.append((sol, 'FAIL', '', '', 'DN create failed'))
        continue
    new_dn = r_dn_c.json().get('data', {}).get('name', '')
    print(f'  ✓ DN: {new_dn}')

    # Submit
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, json={'docstatus': 1}, timeout=60)
    if r_sub.status_code == 200:
        d = r_sub.json().get('data', {})
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if not awb:
            time.sleep(3)
            r_c = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            d2 = r_c.json().get('data', {})
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
        print(f'  ✓ AWB={awb} via {courier}')
        results.append((sol, 'OK', new_dn, awb, courier))
    else:
        print(f'  ✗ Submit FAIL: {r_sub.status_code} {r_sub.text[:200]}')
        results.append((sol, 'FAIL', new_dn, '', 'Submit failed'))
    time.sleep(1)

# ============================================================
# GROUP B: Ghost SKU - SOL1205375
# ============================================================
print(f'\n{"="*70}')
print(f'=== SOL1205375 | GHOST SKU FIX ===')
sol = 'SOL1205375'
ghost_child = '4n37aqn8se'

# Find correct SKU from Shopify
r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
    params={'filters': json.dumps([['shopify_order_number','=',sol]]),
            'fields': json.dumps(['name','shopify_order_id','customer','shipping_address_name',
                                  'custom_order_type','grand_total','taxes_and_charges']),
            'limit_page_length': 1}, timeout=15)
so = r_so.json().get('data', [{}])[0]
so_name = so['name']
shopify_oid = so.get('shopify_order_id', '')
customer = so.get('customer', '')

r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
sh_order = r_sh.json().get('order', {})
for li in sh_order.get('line_items', []):
    sku = li.get('sku', '')
    print(f'  Shopify item: {sku} x{li.get("quantity",0)} @ {li.get("price","")}')

# Identify ghost = the SKU that's NOT SOL-CKW-WSPA-101
correct_sku = ''
for li in sh_order.get('line_items', []):
    sku = li.get('sku', '')
    if sku and sku != 'SOL-CKW-WSPA-101':
        correct_sku = sku
        break

if correct_sku:
    print(f'  Ghost -> {correct_sku}')
    r_item = requests.get(f'{BASE}/api/resource/Item/{correct_sku}', headers=H, timeout=10)
    item_data = r_item.json().get('data', {})
    item_name = item_data.get('item_name', correct_sku)
    uom = item_data.get('stock_uom', 'Nos')

    sn = 'tmp_ghost_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','item_code','" + correct_sku + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','item_name','" + item_name.replace("'","\\'") + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','description','" + item_name.replace("'","\\'") + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','uom','" + uom + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','stock_uom','" + uom + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + ghost_child + "','warehouse','Main Warehouse - WTBBPL',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='fixed'"
    )
    msg = run_server_script(sn, script)
    print(f'  Ghost fix: {msg}')

    # Create DN
    r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so2.json().get('data', {})
    dn_items = []
    for it in so_full.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic: continue
        dn_items.append({'item_code': ic, 'qty': it.get('qty',0), 'rate': it.get('rate',0),
            'against_sales_order': so_name, 'so_detail': it.get('name',''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL')})

    dn_payload = {
        'customer': customer, 'shopify_order_id': shopify_oid, 'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': so.get('shipping_address_name', ''),
        'customer_address': so.get('shipping_address_name', ''),
        'custom_order_type': so.get('custom_order_type', 'Prepaid'),
        'items': dn_items, 'taxes_and_charges': so.get('taxes_and_charges', ''),
    }
    r_dn_c = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn_c.status_code in (200, 201):
        new_dn = r_dn_c.json().get('data', {}).get('name', '')
        print(f'  ✓ DN: {new_dn}')
        r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, json={'docstatus': 1}, timeout=60)
        if r_sub.status_code == 200:
            time.sleep(3)
            r_c = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
                params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            d2 = r_c.json().get('data', {})
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
            print(f'  ✓ AWB={awb} via {courier}')
            results.append((sol, 'OK', new_dn, awb, courier))
        else:
            print(f'  ✗ Submit FAIL: {r_sub.status_code} {r_sub.text[:200]}')
            results.append((sol, 'FAIL', new_dn, '', 'Submit failed'))
    else:
        print(f'  ✗ DN create FAIL: {r_dn_c.status_code} {r_dn_c.text[:200]}')
        results.append((sol, 'FAIL', '', '', 'DN create failed'))

time.sleep(1)

# ============================================================
# GROUP C: SOL1205250 - Delhivery rejected 600099, force Bluedart
# ============================================================
print(f'\n{"="*70}')
print(f'=== SOL1205250 | FORCE BLUEDART ===')
sol = 'SOL1205250'
dn_name = 'SHPDN27-14086'

r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
    params={'filters': json.dumps([['shopify_order_number','=',sol]]),
            'fields': json.dumps(['name','grand_total','shopify_order_id','shipping_address_name']),
            'limit_page_length': 1}, timeout=15)
so = r_so.json().get('data', [{}])[0]
shopify_oid = so.get('shopify_order_id', '')

r_dnf = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=30)
d = r_dnf.json().get('data', {})
addr_name = d.get('shipping_address_name', '')
r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
addr = r_a.json().get('data', {})

drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
pin = str(addr.get('pincode', ''))
phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(phone) > 10: phone = phone[-10:]

items_list = d.get('items', [])
total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
if total_weight <= 0: total_weight = len(items_list) * 0.5
total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
if total_weight_g < 200: total_weight_g = 500
grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)

print(f'  {d.get("customer_name","")} | PIN={pin} | Weight={total_weight_g}g')

cp_payload = {
    'pickup_info': {
        'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
        'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
        'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
        'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-09T10:00:00Z',
    },
    'drop_info': {
        'drop_name': d.get('customer_name', ''), 'drop_phone': phone,
        'drop_address': drop_address, 'drop_city': addr.get('city', ''),
        'drop_state': addr.get('state', ''), 'drop_pincode': pin,
        'drop_country': 'IN', 'drop_email': addr.get('email_id', '') or 'noreply@solara.in',
    },
    'shipment_details': {
        'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': sol,
        'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
        'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                   'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
        'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': 5,
        'invoice_number': dn_name, 'invoice_date': d.get('posting_date', ''),
    },
    'gst_info': {
        'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(d.get('net_total', 0) or 0),
        'ewaybill_serial_number': '', 'is_seller_registered_under_gst': True,
        'place_of_supply': addr.get('state', ''), 'cstin': '',
        'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
        'sgst_amount': 0, 'cgst_amount': 0,
        'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
        'invoice_number': dn_name, 'invoice_date': d.get('posting_date', ''), 'hsn_code': '',
    },
    'additional': {
        'label': True,
        'return_info': {
            'name': 'WIN THE BUY BOX PVT LTD', 'phone': '9573652101',
            'address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
            'city': 'Hyderabad', 'state': 'Telangana', 'pincode': '501218', 'country': 'IN',
        },
        'async': False,
    },
}

r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
    json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
cp_resp = r_cp.json()
meta = cp_resp.get('meta', {})

if meta.get('success') and meta.get('status') == 200:
    new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
    print(f'  ✓ AWB={new_awb} via Bluedart')
    sn = 'tmp_awb_' + dn_name.replace('-','_').lower()
    script = (
        "frappe.db.set_value('Delivery Note','" + dn_name + "','awb_number','" + new_awb + "',update_modified=False)\n"
        "frappe.db.set_value('Delivery Note','" + dn_name + "','courier_partner','Bluedart',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    run_server_script(sn, script)

    # Shopify fulfillment
    if shopify_oid:
        tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
        r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
        fos = r_fo.json().get('fulfillment_orders', [])
        open_fos = []
        for fo in fos:
            if fo.get('status') in ('open', 'in_progress'):
                fo_items = [{'id': li['id'], 'quantity': li.get('fulfillable_quantity',0)}
                           for li in fo.get('line_items',[]) if li.get('fulfillable_quantity',0) > 0]
                if fo_items:
                    open_fos.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_items})
        if open_fos:
            payload = {'fulfillment': {'line_items_by_fulfillment_order': open_fos,
                'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': 'Bluedart'},
                'notify_customer': True}}
            r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
            if r_f.status_code in (200, 201):
                print(f'  ✓ Shopify fulfilled')
            else:
                print(f'  Shopify FAIL: {r_f.status_code} {r_f.text[:200]}')

    results.append((sol, 'OK', dn_name, new_awb, 'Bluedart'))
else:
    err = meta.get('message', '')
    print(f'  ✗ Bluedart FAIL: {err}')
    # Try Delhivery fallback
    cp_payload['shipment_details']['courier_partner'] = 4
    r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
    cp2 = r_cp2.json()
    if cp2.get('meta',{}).get('success'):
        new_awb = str(cp2.get('result',{}).get('waybill',''))
        print(f'  ✓ AWB={new_awb} via Delhivery (fallback)')
        sn = 'tmp_awb_' + dn_name.replace('-','_').lower()
        script = (
            "frappe.db.set_value('Delivery Note','" + dn_name + "','awb_number','" + new_awb + "',update_modified=False)\n"
            "frappe.db.set_value('Delivery Note','" + dn_name + "','courier_partner','Delhivery',update_modified=False)\n"
            "frappe.db.commit()\n"
            "frappe.response['message']='ok'"
        )
        run_server_script(sn, script)
        results.append((sol, 'OK', dn_name, new_awb, 'Delhivery'))
    else:
        print(f'  ✗ Both failed')
        results.append((sol, 'FAIL', dn_name, '', 'Both couriers failed'))

print(f'\n\n{"="*70}')
print('FULL SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]}')
    else:
        print(f'  ✗ {r[0]}: {r[4]}')
print(f'\nNOT SERVICEABLE (CS follow-up):')
print(f'  SOL1205358 (sindhu d, 532440 Srikakulam AP)')
print(f'  SOL1205246 (Devaraju P, 522020 Guntur AP)')
