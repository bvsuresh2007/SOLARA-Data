import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'    Script create failed: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(6)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    if exc:
        print(f'    Script error: {exc[:300]}')
        return None
    return msg

# ============================================================
# First: Pull full Shopify details for all 4 orders
# ============================================================
shopify_orders = {
    'SOL1208231': '7098550354152',
    'SOL1208143': '7098092945640',
    'SOL1208069': '7097871368424',
    'SOL1208005': '7097049678056',
}

shopify_data = {}
for sol, oid in shopify_orders.items():
    r = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}.json', headers=SHOP_H, timeout=30)
    o = r.json().get('order', {})
    shopify_data[sol] = o
    sa = o.get('shipping_address', {})
    print(f'{sol}: {sa.get("name")} | {sa.get("city")} {sa.get("province")} {sa.get("zip")} | Items: {len(o.get("line_items",[]))}')
    for li in o.get('line_items', []):
        print(f'  {li.get("sku","")} x{li.get("quantity")} @ Rs {li.get("price")}')

# ============================================================
# SOL1208231 — No SO, create manually
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208231 — Creating SO ===')
sol = 'SOL1208231'
oid = '7098550354152'
o = shopify_data[sol]
sa = o.get('shipping_address', {})
s_name = sa.get('name', '')
s_addr1 = sa.get('address1', '')
s_addr2 = sa.get('address2', '')
s_city = sa.get('city', '')
s_state = sa.get('province', '')
s_zip = str(sa.get('zip', '')).strip()
s_phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(s_phone) > 10: s_phone = s_phone[-10:]
s_email = o.get('email', '') or 'noreply@solara.in'

# Create customer
cust_name = s_name
r_ce = requests.get(f'{BASE}/api/resource/Customer/{cust_name}', headers=H, timeout=15)
if r_ce.status_code != 200:
    r_cc = requests.post(f'{BASE}/api/resource/Customer', headers=H, json={
        'customer_name': cust_name, 'customer_type': 'Individual',
        'customer_group': 'Individual', 'territory': 'India',
        'gst_category': 'Unregistered',
    }, timeout=15)
    if r_cc.status_code == 200:
        cust_name = r_cc.json().get('data', {}).get('name', cust_name)
        print(f'  Customer created: {cust_name}')
    else:
        print(f'  Customer create failed: {r_cc.status_code} {r_cc.text[:200]}')
else:
    print(f'  Customer exists: {cust_name}')

# Create address
addr_name = f'{cust_name}-{sol}-Shipping'
addr_payload = {
    'name': addr_name, 'address_title': cust_name, 'address_type': 'Shipping',
    'address_line1': s_addr1 or s_name, 'address_line2': s_addr2 or '',
    'city': s_city or 'Unknown', 'state': s_state or '', 'pincode': s_zip,
    'country': 'India', 'phone': s_phone, 'email_id': s_email,
    'is_shipping_address': 1, 'links': [{'link_doctype': 'Customer', 'link_name': cust_name}],
}
r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
if r_ae.status_code == 200:
    requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
    print(f'  Address updated: {addr_name}')
else:
    r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_ac.status_code == 200:
        addr_name = r_ac.json().get('data', {}).get('name', addr_name)
        print(f'  Address created: {addr_name}')
    else:
        print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')

# Build SO items from Shopify line_items
# User specified: SOL-AF-501-CVR-BAG, SOL-AF-501-SIL-BASKET-P6-SPY-101
so_items = []
for li in o.get('line_items', []):
    sku = li.get('sku', '')
    if not sku:
        continue
    so_items.append({
        'item_code': sku,
        'qty': li.get('quantity', 1),
        'rate': float(li.get('price', 0)),
        'delivery_date': '2026-05-20',
        'warehouse': 'Main Warehouse - WTBBPL',
    })

total_price = float(o.get('total_price', 0))
so_payload = {
    'customer': cust_name,
    'transaction_date': o.get('created_at', '')[:10],
    'delivery_date': '2026-05-20',
    'company': 'Win The Buy Box Pvt Ltd',
    'order_type': 'Sales',
    'currency': 'INR',
    'selling_price_list': 'Standard Selling',
    'customer_address': addr_name,
    'shipping_address_name': addr_name,
    'taxes_and_charges': 'Shopify IGST 18% Inclusive - WTBBPL',
    'custom_order_type': 'Prepaid',
    'items': so_items,
}
# Create SO WITHOUT shopify_order_id to avoid "Force Shopify D2C Customer" hook
r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
if r_so.status_code != 200:
    print(f'  SO create failed: {r_so.status_code} {r_so.text[:400]}')
else:
    so_name_231 = r_so.json().get('data', {}).get('name', '')
    print(f'  SO created: {so_name_231}')
    # Submit SO
    r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name_231}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code == 200:
        print(f'  SO submitted!')
    else:
        print(f'  SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
    # Set shopify_order_id after submit via server script
    script = (
        f"frappe.db.set_value('Sales Order','{so_name_231}','shopify_order_id','{oid}',update_modified=False)\n"
        f"frappe.db.set_value('Sales Order','{so_name_231}','shopify_order_number','{sol}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script('tmp_soid_8231', script)
    print(f'  Shopify IDs set: {msg}')

# ============================================================
# SOL1208005 — No SO, create manually
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208005 — Creating SO ===')
sol = 'SOL1208005'
oid = '7097049678056'
o = shopify_data[sol]
sa = o.get('shipping_address', {})
s_name = sa.get('name', '')
s_addr1 = sa.get('address1', '')
s_addr2 = sa.get('address2', '')
s_city = sa.get('city', '')
s_state = sa.get('province', '')
s_zip = str(sa.get('zip', '')).strip()
s_phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(s_phone) > 10: s_phone = s_phone[-10:]
s_email = o.get('email', '') or 'noreply@solara.in'

cust_name_005 = s_name
r_ce = requests.get(f'{BASE}/api/resource/Customer/{cust_name_005}', headers=H, timeout=15)
if r_ce.status_code != 200:
    r_cc = requests.post(f'{BASE}/api/resource/Customer', headers=H, json={
        'customer_name': cust_name_005, 'customer_type': 'Individual',
        'customer_group': 'Individual', 'territory': 'India',
        'gst_category': 'Unregistered',
    }, timeout=15)
    if r_cc.status_code == 200:
        cust_name_005 = r_cc.json().get('data', {}).get('name', cust_name_005)
        print(f'  Customer created: {cust_name_005}')
    else:
        print(f'  Customer create failed: {r_cc.status_code} {r_cc.text[:200]}')
else:
    print(f'  Customer exists: {cust_name_005}')

addr_name_005 = f'{cust_name_005}-{sol}-Shipping'
addr_payload = {
    'name': addr_name_005, 'address_title': cust_name_005, 'address_type': 'Shipping',
    'address_line1': s_addr1 or s_name, 'address_line2': s_addr2 or '',
    'city': s_city or 'Unknown', 'state': s_state or '', 'pincode': s_zip,
    'country': 'India', 'phone': s_phone, 'email_id': s_email,
    'is_shipping_address': 1, 'links': [{'link_doctype': 'Customer', 'link_name': cust_name_005}],
}
r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name_005}', headers=H, timeout=15)
if r_ae.status_code == 200:
    requests.put(f'{BASE}/api/resource/Address/{addr_name_005}', headers=H, json=addr_payload, timeout=15)
    print(f'  Address updated: {addr_name_005}')
else:
    r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_ac.status_code == 200:
        addr_name_005 = r_ac.json().get('data', {}).get('name', addr_name_005)
        print(f'  Address created: {addr_name_005}')
    else:
        print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')

so_items_005 = []
for li in o.get('line_items', []):
    sku = li.get('sku', '')
    if not sku:
        continue
    so_items_005.append({
        'item_code': sku,
        'qty': li.get('quantity', 1),
        'rate': float(li.get('price', 0)),
        'delivery_date': '2026-05-20',
        'warehouse': 'Main Warehouse - WTBBPL',
    })

so_payload_005 = {
    'customer': cust_name_005,
    'transaction_date': o.get('created_at', '')[:10],
    'delivery_date': '2026-05-20',
    'company': 'Win The Buy Box Pvt Ltd',
    'order_type': 'Sales',
    'currency': 'INR',
    'selling_price_list': 'Standard Selling',
    'customer_address': addr_name_005,
    'shipping_address_name': addr_name_005,
    'taxes_and_charges': 'Shopify IGST 18% Inclusive - WTBBPL',
    'custom_order_type': 'Prepaid',
    'items': so_items_005,
}
r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload_005, timeout=30)
if r_so.status_code != 200:
    print(f'  SO create failed: {r_so.status_code} {r_so.text[:400]}')
else:
    so_name_005 = r_so.json().get('data', {}).get('name', '')
    print(f'  SO created: {so_name_005}')
    r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name_005}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code == 200:
        print(f'  SO submitted!')
    else:
        print(f'  SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
    script = (
        f"frappe.db.set_value('Sales Order','{so_name_005}','shopify_order_id','{oid}',update_modified=False)\n"
        f"frappe.db.set_value('Sales Order','{so_name_005}','shopify_order_number','{sol}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script('tmp_soid_8005', script)
    print(f'  Shopify IDs set: {msg}')

# ============================================================
# Now create DNs + AWBs for all 4
# ============================================================
# Collect all SOs
all_orders = []

# SOL1208231
r_s = requests.get(f'{BASE}/api/resource/Sales Order', headers=H, params={
    'filters': json.dumps([['shopify_order_number', '=', 'SOL1208231']]),
    'fields': json.dumps(['name', 'shipping_address_name', 'shopify_order_id', 'customer_name']),
}, timeout=15)
d = r_s.json().get('data', [])
if d:
    all_orders.append(('SOL1208231', d[0]['name'], d[0].get('shopify_order_id','7098550354152'), d[0].get('shipping_address_name',''), []))

# SOL1208143 — has 2 draft DNs to delete
all_orders.append(('SOL1208143', 'SHP27-14430', '7098092945640', '', ['SHPDN27-17353', 'SHPDN27-17358']))

# SOL1208069 — no DN
all_orders.append(('SOL1208069', 'SHP27-14356', '7097871368424', '', []))

# SOL1208005
r_s = requests.get(f'{BASE}/api/resource/Sales Order', headers=H, params={
    'filters': json.dumps([['shopify_order_number', '=', 'SOL1208005']]),
    'fields': json.dumps(['name', 'shipping_address_name', 'shopify_order_id', 'customer_name']),
}, timeout=15)
d = r_s.json().get('data', [])
if d:
    all_orders.append(('SOL1208005', d[0]['name'], d[0].get('shopify_order_id','7097049678056'), d[0].get('shipping_address_name',''), []))

results = []

for sol, so_name, shopify_oid, addr_override, draft_dns in all_orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} — DN + AWB ===')

    # Get SO details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so = r_so.json().get('data', {})
    addr_name = addr_override or so.get('shipping_address_name', '')
    cust = so.get('customer', '')
    print(f'  {so.get("customer_name")} | addr={addr_name}')

    # Delete draft DNs
    for ddn in draft_dns:
        r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{ddn}', headers=H, timeout=15)
        print(f'  Deleted draft {ddn}: {r_del.status_code}')

    # Reset per_delivered if needed
    per_del = float(so.get('per_delivered', 0) or 0)
    if per_del > 0:
        lines = [f"frappe.db.set_value('Sales Order','{so_name}','per_delivered',0,update_modified=False)"]
        lines.append(f"frappe.db.set_value('Sales Order','{so_name}','status','To Deliver and Bill',update_modified=False)")
        for item in so.get('items', []):
            iname = item.get('name', '')
            lines.append(f"frappe.db.set_value('Sales Order Item','{iname}','delivered_qty',0,update_modified=False)")
        lines.append("frappe.db.commit()")
        lines.append("frappe.response['message']='ok'")
        msg = run_server_script(f'tmp_rst_{sol[-4:]}', "\n".join(lines))
        print(f'  Reset per_delivered: {msg}')

    # Create DN from SO
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        results.append((sol, '', '', 'DN_MAKE_FAIL'))
        continue

    dn_draft = r_dn.json().get('message', {})
    if not dn_draft.get('items'):
        print(f'  No items in DN draft!')
        results.append((sol, '', '', 'NO_ITEMS'))
        continue

    dn_draft['shipping_address_name'] = addr_name
    dn_draft['customer_address'] = addr_name
    dn_draft['shopify_order_id'] = shopify_oid
    dn_draft['shopify_order_number'] = sol

    for tax in dn_draft.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        print(f'  DN save failed: {r3.status_code} {r3.text[:400]}')
        results.append((sol, '', '', 'DN_SAVE_FAIL'))
        continue

    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

    # Submit DN
    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'  DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'  DN submitted (417 OK)!')
        else:
            print(f'  DN submit failed: {r4.text[:300]}')
            results.append((sol, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((sol, dn_name, '', 'DN_SUBMIT_FAIL'))
        continue

    # Check AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    dd = r6.json().get('data', {})
    awb = dd.get('awb_number', '')
    courier = dd.get('courier_partner', '')

    if not awb:
        print(f'  No auto-AWB, creating manually...')
        r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
        dn_data = r_dn2.json().get('data', {})
        items_list = dn_data.get('items', [])
        grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
        net_total = float(dn_data.get('net_total', 0) or 0)
        total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)
        posting_date = dn_data.get('posting_date', '')

        r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
        addr = r_a.json().get('data', {})
        pin = str(addr.get('pincode', ''))
        drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
        phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(phone) > 10: phone = phone[-10:]
        city = addr.get('city', '')
        state = addr.get('state', '')
        email_addr = addr.get('email_id', '') or 'noreply@solara.in'
        drop_name = addr.get('address_title', '') or cust

        for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
            cp_payload = {
                'pickup_info': {
                    'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                    'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                    'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-17T10:00:00Z',
                },
                'drop_info': {
                    'drop_name': drop_name, 'drop_phone': phone,
                    'drop_address': drop_address, 'drop_city': city,
                    'drop_state': state, 'drop_pincode': pin,
                    'drop_country': 'IN', 'drop_email': email_addr,
                },
                'shipment_details': {
                    'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': sol,
                    'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                    'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                               'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                    'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                    'invoice_number': dn_name, 'invoice_date': posting_date,
                },
                'gst_info': {
                    'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': net_total,
                    'is_seller_registered_under_gst': True, 'place_of_supply': state,
                    'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                    'sgst_amount': 0, 'cgst_amount': 0, 'igst_amount': total_taxes,
                    'invoice_number': dn_name, 'invoice_date': posting_date,
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
            print(f'    Trying {cp_name}...')
            r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
            cp_resp = r_cp.json()
            meta = cp_resp.get('meta', {})
            if meta.get('success') and meta.get('status') == 200:
                awb = str(cp_resp.get('result', {}).get('waybill', ''))
                courier = cp_name
                print(f'    SUCCESS! AWB={awb} via {courier}')
                break
            else:
                err = meta.get('message', '')
                print(f'    FAIL {cp_name}: {err[:200]}')
                if 'already placed' in err.lower():
                    cp_payload['shipment_details']['reference_number'] = sol + '-R1'
                    r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                    meta2 = r_cp2.json().get('meta', {})
                    if meta2.get('success') and meta2.get('status') == 200:
                        awb = str(r_cp2.json().get('result', {}).get('waybill', ''))
                        courier = cp_name
                        print(f'    SUCCESS with -R1! AWB={awb} via {courier}')
                        break

        if awb:
            script = (
                f"frappe.db.set_value('Delivery Note','{dn_name}','awb_number','{awb}',update_modified=False)\n"
                f"frappe.db.set_value('Delivery Note','{dn_name}','courier_partner','{courier}',update_modified=False)\n"
                f"frappe.db.commit()\n"
                f"frappe.response['message']='ok'"
            )
            msg = run_server_script(f'tmp_awb_{sol[-4:]}', script)
            print(f'    DN AWB saved: {msg}')

    if awb:
        print(f'  AWB={awb} via {courier}')
        results.append((sol, dn_name, awb, courier))

        # Sync to Shopify
        tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
        r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
        fos = r_fo.json().get('fulfillment_orders', [])
        open_fos = [fo for fo in fos if fo.get('status') in ('open', 'in_progress')]
        if open_fos:
            line_items_by_fo = []
            for fo in open_fos:
                fo_lines = [{'id': li['id'], 'quantity': li['fulfillable_quantity']} for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
                if fo_lines:
                    line_items_by_fo.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_lines})
            if line_items_by_fo:
                ful_payload = {
                    'fulfillment': {
                        'line_items_by_fulfillment_order': line_items_by_fo,
                        'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                        'notify_customer': True,
                    }
                }
                r_cf = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=ful_payload, timeout=30)
                print(f'  Shopify fulfillment: {r_cf.status_code}')
                if r_cf.status_code in (200, 201):
                    ful_id = r_cf.json().get('fulfillment', {}).get('id', '')
                    time.sleep(1)
                    payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': False}}
                    requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                    print(f'  Shopify 2nd push done')
        else:
            r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
            fuls = r_ful.json().get('fulfillments', [])
            if fuls:
                ful_id = str(fuls[-1].get('id', ''))
                payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
                r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                print(f'  Shopify tracking updated: {r_u.status_code}')
    else:
        print(f'  ALL COURIERS FAILED')
        results.append((sol, dn_name, '', 'AWB_FAIL'))

print(f'\n\n{"="*60}')
print('SUMMARY')
print(f'{"="*60}')
for sol, dn, awb, courier in results:
    print(f'  {sol} | DN={dn} | AWB={awb} | {courier}')
