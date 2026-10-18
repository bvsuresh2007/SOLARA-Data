import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'
COMPANY = 'Win The Buy Box Private Limited'

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

def create_awb_and_sync(sol, so_name, shopify_oid, dn_name, addr_name):
    """Check AWB, create manually if needed, sync to Shopify"""
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
        drop_name = addr.get('address_title', '')

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
    return awb, courier

def pull_shopify_addr(oid):
    r = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}.json', headers=SHOP_H,
        params={'fields': 'id,name,shipping_address,email'}, timeout=30)
    o = r.json().get('order', {})
    sa = o.get('shipping_address', {})
    phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10: phone = phone[-10:]
    return {
        'name': sa.get('name',''), 'addr1': sa.get('address1',''), 'addr2': sa.get('address2',''),
        'city': sa.get('city',''), 'state': sa.get('province',''), 'zip': str(sa.get('zip','')).strip(),
        'phone': phone, 'email': o.get('email','') or 'noreply@solara.in',
    }

def create_update_address(cust, sol, sa):
    addr_name = f'{cust}-{sol}-Shipping'
    addr_payload = {
        'address_title': cust, 'address_type': 'Shipping',
        'address_line1': sa['addr1'] or sa['name'], 'address_line2': sa.get('addr2',''),
        'city': sa['city'] or 'Unknown', 'state': sa['state'] or '', 'pincode': sa['zip'],
        'country': 'India', 'phone': sa['phone'], 'email_id': sa['email'],
        'is_shipping_address': 1, 'links': [{'link_doctype': 'Customer', 'link_name': cust}],
    }
    r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    if r_ae.status_code == 200:
        r_au = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        addr_name = r_au.json().get('data', {}).get('name', addr_name) if r_au.status_code == 200 else addr_name
        print(f'  Address updated: {addr_name}')
    else:
        addr_payload['name'] = addr_name
        r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r_ac.status_code == 200:
            addr_name = r_ac.json().get('data', {}).get('name', addr_name)
            print(f'  Address created: {addr_name}')
        else:
            print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')
    return addr_name

def create_so_without_hook(cust, sol, oid, sa, items, tax_template):
    """Create SO without shopify_order_id (avoids hook), then set it after submit"""
    so_payload = {
        'customer': cust,
        'transaction_date': '2026-05-17',
        'delivery_date': '2026-05-20',
        'company': COMPANY,
        'order_type': 'Sales',
        'currency': 'INR',
        'selling_price_list': 'Standard Selling',
        'customer_address': sa['addr_name'],
        'shipping_address_name': sa['addr_name'],
        'taxes_and_charges': tax_template,
        'custom_order_type': 'Prepaid',
        'items': items,
    }
    r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
    if r_so.status_code != 200:
        print(f'  SO create failed: {r_so.status_code} {r_so.text[:400]}')
        return None
    so_name = r_so.json().get('data', {}).get('name', '')
    print(f'  SO created: {so_name}')

    r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code == 200:
        print(f'  SO submitted!')
    else:
        print(f'  SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
        return so_name

    script = (
        f"frappe.db.set_value('Sales Order','{so_name}','shopify_order_id','{oid}',update_modified=False)\n"
        f"frappe.db.set_value('Sales Order','{so_name}','shopify_order_number','{sol}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script(f'tmp_soid_{sol[-4:]}', script)
    print(f'  Shopify IDs set: {msg}')
    return so_name

def create_dn_submit(so_name, addr_name, shopify_oid, sol):
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        return None
    dn_draft = r_dn.json().get('message', {})
    if not dn_draft.get('items'):
        print(f'  No items in DN draft!')
        return None
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
        print(f'  DN save failed: {r3.status_code} {r3.text[:300]}')
        return None
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

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
            return None
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        return None
    return dn_name

results = []

# ============================================================
# 1. SOL1208231 — Create SO (company fix)
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208231 ===')
sol, oid = 'SOL1208231', '7098550354152'
sa = pull_shopify_addr(oid)
print(f'  {sa["name"]} | {sa["city"]} {sa["state"]} {sa["zip"]}')
cust = 'Afnan Masood'  # Already created
addr_name = create_update_address(cust, sol, sa)
sa['addr_name'] = addr_name
items = [
    {'item_code': 'SOL-AF-501-CVR-BAG', 'qty': 1, 'rate': 499.0, 'delivery_date': '2026-05-20', 'warehouse': 'Main Warehouse - WTBBPL'},
    {'item_code': 'SOL-AF-501-SIL-BASKET-P6-SPY-101', 'qty': 1, 'rate': 8199.0, 'delivery_date': '2026-05-20', 'warehouse': 'Main Warehouse - WTBBPL'},
]
so_name = create_so_without_hook(cust, sol, oid, sa, items, 'Shopify IGST 18% Inclusive - WTBBPL')
if so_name:
    dn_name = create_dn_submit(so_name, addr_name, oid, sol)
    if dn_name:
        awb, courier = create_awb_and_sync(sol, so_name, oid, dn_name, addr_name)
        results.append((sol, dn_name, awb, courier))
    else:
        results.append((sol, '', '', 'DN_FAIL'))
else:
    results.append((sol, '', '', 'SO_FAIL'))

# ============================================================
# 2. SOL1208005 — Create SO (company fix)
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208005 ===')
sol, oid = 'SOL1208005', '7097049678056'
sa = pull_shopify_addr(oid)
print(f'  {sa["name"]} | {sa["city"]} {sa["state"]} {sa["zip"]}')
cust = 'SAJAN SIMON'  # Already created
addr_name = create_update_address(cust, sol, sa)
sa['addr_name'] = addr_name
items = [
    {'item_code': 'SOL-INS-WB-301', 'qty': 1, 'rate': 1999.0, 'delivery_date': '2026-05-20', 'warehouse': 'Main Warehouse - WTBBPL'},
    {'item_code': 'SOL-INS-PERSONALISATION', 'qty': 1, 'rate': 100.0, 'delivery_date': '2026-05-20', 'warehouse': 'Main Warehouse - WTBBPL'},
]
so_name = create_so_without_hook(cust, sol, oid, sa, items, 'Shopify IGST 18% Inclusive - WTBBPL')
if so_name:
    dn_name = create_dn_submit(so_name, addr_name, oid, sol)
    if dn_name:
        awb, courier = create_awb_and_sync(sol, so_name, oid, dn_name, addr_name)
        results.append((sol, dn_name, awb, courier))
    else:
        results.append((sol, '', '', 'DN_FAIL'))
else:
    results.append((sol, '', '', 'SO_FAIL'))

# ============================================================
# 3. SOL1208143 — Fix address PIN, retry DN
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208143 ===')
sol, oid, so_name = 'SOL1208143', '7098092945640', 'SHP27-14430'
sa = pull_shopify_addr(oid)
print(f'  {sa["name"]} | {sa["city"]} {sa["state"]} {sa["zip"]}')

# Get customer
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, params={
    'fields': json.dumps(['customer'])
}, timeout=15)
cust = r_so.json().get('data', {}).get('customer', '')
addr_name = create_update_address(cust, sol, sa)

# Update SO address
script = (
    f"frappe.db.set_value('Sales Order','{so_name}','shipping_address_name','{addr_name}',update_modified=False)\n"
    f"frappe.db.set_value('Sales Order','{so_name}','customer_address','{addr_name}',update_modified=False)\n"
    f"frappe.db.commit()\n"
    f"frappe.response['message']='ok'"
)
msg = run_server_script('tmp_addr_8143', script)
print(f'  SO address updated: {msg}')

# Delete the draft DN from earlier attempt
requests.delete(f'{BASE}/api/resource/Delivery Note/SHPDN27-17574', headers=H, timeout=15)
print(f'  Deleted draft SHPDN27-17574')

# Reset per_delivered
r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
so_data = r_so_full.json().get('data', {})
per_del = float(so_data.get('per_delivered', 0) or 0)
if per_del > 0:
    lines = [f"frappe.db.set_value('Sales Order','{so_name}','per_delivered',0,update_modified=False)"]
    lines.append(f"frappe.db.set_value('Sales Order','{so_name}','status','To Deliver and Bill',update_modified=False)")
    for item in so_data.get('items', []):
        iname = item.get('name', '')
        lines.append(f"frappe.db.set_value('Sales Order Item','{iname}','delivered_qty',0,update_modified=False)")
    lines.append("frappe.db.commit()")
    lines.append("frappe.response['message']='ok'")
    msg = run_server_script('tmp_rst_8143', "\n".join(lines))
    print(f'  Reset per_delivered: {msg}')

dn_name = create_dn_submit(so_name, addr_name, oid, sol)
if dn_name:
    awb, courier = create_awb_and_sync(sol, so_name, oid, dn_name, addr_name)
    results.append((sol, dn_name, awb, courier))
else:
    results.append((sol, '', '', 'DN_FAIL'))

# ============================================================
# 4. SOL1208069 — Fix item_code on SO, create DN
# ============================================================
print(f'\n{"="*60}')
print(f'=== SOL1208069 ===')
sol, oid, so_name = 'SOL1208069', '7097871368424', 'SHP27-14356'
sa = pull_shopify_addr(oid)
print(f'  {sa["name"]} | {sa["city"]} {sa["state"]} {sa["zip"]}')

# Fix item_code on SO item via server script
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
so_data = r_so.json().get('data', {})
cust = so_data.get('customer', '')
addr_name_069 = so_data.get('shipping_address_name', '')

# Update address to match Shopify
addr_name_069 = create_update_address(cust, sol, sa)
script = (
    f"frappe.db.set_value('Sales Order','{so_name}','shipping_address_name','{addr_name_069}',update_modified=False)\n"
    f"frappe.db.set_value('Sales Order','{so_name}','customer_address','{addr_name_069}',update_modified=False)\n"
    f"frappe.db.commit()\n"
    f"frappe.response['message']='ok'"
)
msg = run_server_script('tmp_addr_8069', script)
print(f'  SO address updated: {msg}')

# Fix the None item_code
for item in so_data.get('items', []):
    if not item.get('item_code'):
        iname = item.get('name', '')
        script = (
            f"frappe.db.set_value('Sales Order Item','{iname}','item_code','SOL-INS-TUM-202R',update_modified=False)\n"
            f"frappe.db.set_value('Sales Order Item','{iname}','item_name','Insulated Water Bottles (Refurbished) - Elixir / Dusky Pink',update_modified=False)\n"
            f"frappe.db.commit()\n"
            f"frappe.response['message']='ok'"
        )
        msg = run_server_script('tmp_fix_item_8069', script)
        print(f'  Fixed item_code: {msg}')

# Now create DN manually (make_delivery_note won't work with None item)
# Build DN directly
dn_payload = {
    'customer': cust,
    'company': COMPANY,
    'posting_date': '2026-05-17',
    'shipping_address_name': addr_name_069,
    'customer_address': addr_name_069,
    'shopify_order_id': oid,
    'shopify_order_number': sol,
    'taxes_and_charges': so_data.get('taxes_and_charges', 'Shopify IGST 18% Inclusive - WTBBPL'),
    'items': [{
        'item_code': 'SOL-INS-TUM-202R',
        'qty': 1,
        'rate': float(so_data.get('items', [{}])[0].get('rate', 854.15)),
        'warehouse': 'Main Warehouse - WTBBPL',
        'against_sales_order': so_name,
        'so_detail': so_data.get('items', [{}])[0].get('name', ''),
    }],
}

r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
if r3.status_code != 200:
    print(f'  DN save failed: {r3.status_code} {r3.text[:400]}')
    results.append((sol, '', '', 'DN_SAVE_FAIL'))
else:
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')
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
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((sol, dn_name, '', 'DN_SUBMIT_FAIL'))

    if dn_name:
        awb, courier = create_awb_and_sync(sol, so_name, oid, dn_name, addr_name_069)
        results.append((sol, dn_name, awb, courier))

print(f'\n\n{"="*60}')
print('SUMMARY')
print(f'{"="*60}')
for sol, dn, awb, courier in results:
    print(f'  {sol} | DN={dn} | AWB={awb} | {courier}')
