import os, requests, json, sys, time
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
        print(f'  Script create failed: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(6)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    if exc:
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

# ============================================================
# SOL1206059 - has SO SHP27-12362, draft DN SHPDN27-16147
# ============================================================
sol = 'SOL1206059'
so_name = 'SHP27-12362'
draft_dn = 'SHPDN27-16147'
print(f'{"="*70}')
print(f'=== {sol} ===')

# Get SO details
r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
so = r.json().get('data', {})
cust = so.get('customer', '')
shopify_oid = so.get('shopify_order_id', '')
otype = so.get('custom_order_type', 'Prepaid')
cod_amount = float(so.get('custom_cod_amount', 0) or 0)
taxes = so.get('taxes_and_charges', '')
print(f'  SO: {cust} | {otype} | Rs {so.get("grand_total")} | Shopify OID: {shopify_oid}')

# Pull Shopify shipping address
rs = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H,
    params={'fields': 'id,name,shipping_address'}, timeout=30)
sa = rs.json().get('order', {}).get('shipping_address', {})
s_name = sa.get('name', '')
s_addr1 = sa.get('address1', '')
s_addr2 = sa.get('address2', '')
s_city = sa.get('city', '')
s_state = sa.get('province', '')
s_zip = str(sa.get('zip', '')).strip()
s_phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(s_phone) > 10: s_phone = s_phone[-10:]
s_email = sa.get('email', '') or 'noreply@solara.in'
print(f'  Shopify: {s_name} | {s_addr1}, {s_addr2} | {s_city}, {s_state} {s_zip} | Ph: {s_phone}')

# Create/update Address on Atlas
addr_name = f'{cust}-{sol}-Shipping'
r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
addr_payload = {
    'address_title': cust,
    'address_type': 'Shipping',
    'address_line1': s_addr1 or s_name,
    'address_line2': s_addr2 or '',
    'city': s_city or 'Unknown',
    'state': s_state or '',
    'pincode': s_zip,
    'country': 'India',
    'phone': s_phone,
    'email_id': s_email,
    'is_shipping_address': 1,
    'links': [{'link_doctype': 'Customer', 'link_name': cust}],
}
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

# Update SO shipping address
sn = f'tmp_addr_{sol.lower()}'
script = (
    f"frappe.db.set_value('Sales Order','{so_name}','shipping_address_name','{addr_name}',update_modified=False)\n"
    f"frappe.db.set_value('Sales Order','{so_name}','customer_address','{addr_name}',update_modified=False)\n"
    f"frappe.db.commit()\n"
    f"frappe.response['message']='ok'"
)
msg = run_server_script(sn, script)
print(f'  SO address updated: {msg}')

# Delete draft DN and create fresh one
print(f'  Deleting draft DN {draft_dn}...')
r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{draft_dn}', headers=H, timeout=15)
print(f'  Delete: {r_del.status_code}')

# Check per_delivered — reset if needed
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, params={
    'fields': json.dumps(['per_delivered'])
}, timeout=15)
per_del = float(r_so.json().get('data', {}).get('per_delivered', 0) or 0)
if per_del > 0:
    print(f'  per_delivered={per_del}, resetting...')
    lines = [f"frappe.db.set_value('Sales Order','{so_name}','per_delivered',0,update_modified=False)"]
    lines.append(f"frappe.db.set_value('Sales Order','{so_name}','status','To Deliver and Bill',update_modified=False)")
    for item in so.get('items', []):
        iname = item.get('name', '')
        lines.append(f"frappe.db.set_value('Sales Order Item','{iname}','delivered_qty',0,update_modified=False)")
    lines.append("frappe.db.commit()")
    lines.append("frappe.response['message']='ok'")
    msg = run_server_script('tmp_rst_206059', "\n".join(lines))
    print(f'  Reset: {msg}')

# Create DN from SO
r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
    headers=H, params={'source_name': so_name}, timeout=15)
if r_dn.status_code != 200:
    print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
    sys.exit(1)

dn_draft = r_dn.json().get('message', {})
dn_items = dn_draft.get('items', [])
print(f'  DN draft items: {len(dn_items)}')

if not dn_items:
    print(f'  ERROR: No items in DN draft!')
    sys.exit(1)

dn_draft['shipping_address_name'] = addr_name
dn_draft['customer_address'] = addr_name
# Fix taxes
for tax in dn_draft.get('taxes', []):
    if tax.get('item_wise_tax_detail') is None:
        tax['item_wise_tax_detail'] = '{}'
for item in dn_draft.get('items', []):
    item.pop('item_tax_template', None)
for key in ['__islocal', '__unsaved', 'amended_from']:
    dn_draft.pop(key, None)

# Save DN
r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
if r3.status_code != 200:
    print(f'  DN save failed: {r3.status_code} {r3.text[:400]}')
    sys.exit(1)

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
        sys.exit(1)
else:
    print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
    sys.exit(1)

# Check AWB
time.sleep(3)
r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
    'fields': json.dumps(['awb_number', 'courier_partner'])
}, timeout=15)
d = r6.json().get('data', {})
awb = d.get('awb_number', '')
courier = d.get('courier_partner', '')
print(f'  AWB={awb} | {courier}')

# Sync to Shopify
if shopify_oid:
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
        # Check existing fulfillments
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        fuls = r_ful.json().get('fulfillments', [])
        if fuls:
            ful_id = str(fuls[-1].get('id', ''))
            payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'  Shopify tracking updated: {r_u.status_code}')

print(f'\nDONE: {sol} | DN={dn_name} | AWB={awb} via {courier}')

# ============================================================
# SOL1206144 - no SO on Atlas. Check Shopify directly
# ============================================================
print(f'\n\n{"="*70}')
print(f'=== SOL1206144 ===')

# Search Shopify by order number
r_s = requests.get(f'{SHOP}/admin/api/2024-01/orders.json', headers=SHOP_H, params={
    'name': 'SOL1206144', 'status': 'any'
}, timeout=15)
shop_orders = r_s.json().get('orders', [])
if shop_orders:
    for o in shop_orders:
        print(f'  Found: #{o.get("name")} | {o.get("email")} | {o.get("financial_status")} | {o.get("fulfillment_status")}')
        sa = o.get('shipping_address', {})
        print(f'  Ship to: {sa.get("name")} | {sa.get("city")} {sa.get("province")} {sa.get("zip")}')
else:
    print(f'  Not found on Shopify either')
    # Try searching with # prefix
    r_s2 = requests.get(f'{SHOP}/admin/api/2024-01/orders.json', headers=SHOP_H, params={
        'name': '#SOL1206144', 'status': 'any'
    }, timeout=15)
    shop_orders2 = r_s2.json().get('orders', [])
    if shop_orders2:
        for o in shop_orders2:
            print(f'  Found: #{o.get("name")} | {o.get("email")}')
    else:
        print(f'  Not found with # prefix either. Order may not exist on Shopify.')
