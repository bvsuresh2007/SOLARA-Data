import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'
r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}
CUSTOMER = 'Shopify D2C Customer'
COMPANY_ADDRESS = 'Win The Buy Box Private Limited-Billing'
DEFAULT_TAXES = 'GST 18% Interstate - WTBBPL'

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'  Script create FAIL: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(3)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

sol = 'SOL1202028'

# Step 1: Get Shopify order
r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json', headers=SHOP_H, params={'name': sol, 'status': 'any'}, timeout=15)
sh = r_sh.json().get('orders', [])[0]
shopify_oid = str(sh.get('id', ''))
sa = sh.get('shipping_address') or {}
sh_pin = str(sa.get('zip', ''))
sh_addr1 = sa.get('address1', '') or ''
sh_addr2 = sa.get('address2', '') or ''
sh_city = sa.get('city', '') or ''
sh_state = sa.get('province', '') or ''
sh_name = sa.get('name', '') or ''
sh_phone = sa.get('phone', '') or ''
sh_email = sh.get('email', '') or ''
total = float(sh.get('total_price', '0'))

phone = sh_phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(phone) > 10: phone = phone[-10:]

# PPCOD calculation
r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
txns = r_txn.json().get('transactions', [])
captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
cod_amount = round(total - captured, 2)
otype = 'PPCOD'
print(f'Order: {sol} | {sh_name} | {sh_city} {sh_state} PIN={sh_pin}')
print(f'Total={total} Captured={captured} COD={cod_amount} -> {otype}')

# Get line items
so_items = []
for li in sh.get('line_items', []):
    sku = li.get('sku', '')
    if not sku:
        print(f'  WARNING: no SKU for "{li.get("title","")}" — skipping')
        continue
    qty = int(li.get('quantity', 1))
    price = float(li.get('price', '0'))
    rate = round(price / 1.18, 2)
    so_items.append({'item_code': sku, 'qty': qty, 'rate': rate, 'warehouse': 'Main Warehouse - WTBBPL'})

items_str = ', '.join([it['item_code'] + ' x' + str(it['qty']) for it in so_items])
print(f'Items: {items_str}')

# Step 2: Create Address
addr_name = CUSTOMER + '-' + sol + '-Shipping'
requests.delete(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=10)
time.sleep(0.5)

r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json={
    'name': addr_name, 'address_title': sh_name or CUSTOMER, 'address_type': 'Shipping',
    'address_line1': sh_addr1 or 'NA', 'address_line2': sh_addr2,
    'city': sh_city or 'NA', 'state': sh_state, 'pincode': sh_pin,
    'country': 'India', 'phone': phone, 'email_id': sh_email,
    'links': [{'link_doctype': 'Customer', 'link_name': CUSTOMER}],
}, timeout=15)
if r_addr.status_code in (200, 201):
    created_addr = r_addr.json().get('data', {}).get('name', addr_name)
else:
    r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
        params={'filters': json.dumps([['name','like',f'%{sol}%Shipping%']]),
                'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
    found = r_find.json().get('data', [])
    if found:
        created_addr = found[0]['name']
        requests.put(f'{BASE}/api/resource/Address/{created_addr}', headers=H, json={
            'address_line1': sh_addr1 or 'NA', 'address_line2': sh_addr2,
            'city': sh_city or 'NA', 'state': sh_state, 'pincode': sh_pin, 'phone': phone
        }, timeout=15)
    else:
        print(f'Address FAIL: {r_addr.status_code} {r_addr.text[:200]}')
        sys.exit(1)
print(f'Address: {created_addr}')

# Step 3: Create + Submit SO via server script
item_lines = ""
for it in so_items:
    sku = it['item_code'].replace("'", "\\'")
    item_lines += (
        "row = doc.append('items', {})\n"
        "row.item_code = '" + sku + "'\n"
        "row.qty = " + str(it['qty']) + "\n"
        "row.rate = " + str(it['rate']) + "\n"
        "row.warehouse = '" + it['warehouse'] + "'\n"
        "row.delivery_date = '2026-05-12'\n"
    )
sn_so = 'tmp_mkso_s1202028'
script_so = (
    "doc = frappe.new_doc('Sales Order')\n"
    "doc.customer = '" + CUSTOMER + "'\n"
    "doc.shopify_order_id = '" + shopify_oid + "'\n"
    "doc.shopify_order_number = '" + sol + "'\n"
    "doc.custom_shopify_order_number = '" + sol + "'\n"
    "doc.shipping_address_name = '" + created_addr.replace("'", "\\'") + "'\n"
    "doc.customer_address = '" + created_addr.replace("'", "\\'") + "'\n"
    "doc.company_address = '" + COMPANY_ADDRESS + "'\n"
    "doc.custom_order_type = '" + otype + "'\n"
    "doc.delivery_date = '2026-05-12'\n"
    "doc.taxes_and_charges = '" + DEFAULT_TAXES + "'\n"
    "doc.gst_category = 'Unregistered'\n"
    "doc.custom_cod_amount = " + str(cod_amount) + "\n"
    + item_lines +
    "doc.flags.ignore_validate = True\n"
    "doc.flags.ignore_mandatory = True\n"
    "doc.flags.ignore_permissions = True\n"
    "doc.insert(ignore_permissions=True)\n"
    "doc.submit()\n"
    "frappe.db.commit()\n"
    "frappe.response['message'] = doc.name"
)
new_so = run_server_script(sn_so, script_so)
if not new_so or new_so == 'None':
    print('SO create+submit FAIL')
    sys.exit(1)
print(f'SO: {new_so} (submitted)')

# Step 4: Read SO for DN creation
time.sleep(1)
r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{new_so}', headers=H, timeout=15)
so_full = r_so2.json().get('data', {})

dn_items = []
for it in so_full.get('items', []):
    ic = it.get('item_code', '')
    if not ic: continue
    dn_items.append({
        'item_code': ic, 'qty': it.get('qty', 0), 'rate': it.get('rate', 0),
        'against_sales_order': new_so, 'so_detail': it.get('name', ''),
        'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
    })

# Step 5: Create DN
dn_payload = {
    'customer': CUSTOMER,
    'shopify_order_id': shopify_oid, 'shopify_order_number': sol,
    'custom_shopify_order_number': sol,
    'shipping_address_name': created_addr, 'customer_address': created_addr,
    'custom_order_type': otype, 'custom_cod_amount': cod_amount,
    'items': dn_items,
    'taxes_and_charges': so_full.get('taxes_and_charges', ''),
}
r_dn = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
if r_dn.status_code not in (200, 201):
    print(f'DN create FAIL: {r_dn.status_code} {r_dn.text[:300]}')
    sys.exit(1)
new_dn = r_dn.json().get('data', {}).get('name', '')
print(f'DN: {new_dn}')

# Step 6: Submit DN
r_sub_dn = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, json={'docstatus': 1}, timeout=60)
awb = ''
courier = ''
if r_sub_dn.status_code == 200:
    dn_data = r_sub_dn.json().get('data', {})
    awb = dn_data.get('awb_number', '') or ''
    courier = dn_data.get('courier_partner', '') or ''
    print(f'DN submitted | AWB={awb} | {courier}')
else:
    time.sleep(2)
    r_chk = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
        params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
    d2 = r_chk.json().get('data', {})
    if d2.get('docstatus') == 1:
        awb = d2.get('awb_number', '') or ''
        courier = d2.get('courier_partner', '') or ''
        print(f'DN submitted (race) | AWB={awb} | {courier}')
    else:
        print(f'DN submit FAIL: {r_sub_dn.status_code} {r_sub_dn.text[:300]}')
        sys.exit(1)

# Check AWB after delay
if not awb:
    time.sleep(3)
    r_chk2 = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
        params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
    d3 = r_chk2.json().get('data', {})
    awb = d3.get('awb_number', '') or ''
    courier = d3.get('courier_partner', '') or ''
    if awb:
        print(f'AWB (delayed): {awb} via {courier}')

# Manual Clickpost if no AWB
if not awb:
    print('No auto AWB — trying manual Clickpost (Delhivery first)...')
    r_dn_full = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, timeout=15)
    dn_full = r_dn_full.json().get('data', {})
    items_list = dn_full.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0: total_weight = len(items_list) * 0.5
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200: total_weight_g = 500
    grand_total = max(float(dn_full.get('grand_total', 0) or 0), 1.0)

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-12T10:00:00Z',
            },
            'drop_info': {
                'drop_name': sh_name, 'drop_phone': phone,
                'drop_address': (sh_addr1 + ' ' + sh_addr2).strip(), 'drop_city': sh_city,
                'drop_state': sh_state, 'drop_pincode': sh_pin,
                'drop_country': 'IN', 'drop_email': sh_email or 'noreply@solara.in',
            },
            'shipment_details': {
                'order_type': 'COD', 'invoice_value': grand_total, 'reference_number': sol,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_amount, 'courier_partner': cp_id,
                'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''),
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(dn_full.get('net_total', 0) or 0),
                'is_seller_registered_under_gst': True, 'place_of_supply': sh_state,
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0,
                'igst_amount': float(dn_full.get('total_taxes_and_charges', 0) or 0),
                'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''),
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
        print(f'  Trying {cp_name}...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})
        if meta.get('success') and meta.get('status') == 200:
            awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cp_name
            print(f'  AWB={awb} via {courier}')
            sn_awb = 'tmp_nawb_' + new_dn.replace('-','_').lower()
            script_awb = "frappe.db.set_value('Delivery Note','" + new_dn + "','awb_number','" + awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + new_dn + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
            run_server_script(sn_awb, script_awb)
            print(f'  AWB saved to DN')
            break
        else:
            print(f'  FAIL {cp_name}: {meta.get("message","")[:200]}')

if not awb:
    print('ALL FAILED — no AWB')
    sys.exit(1)

# Shopify fulfillment
tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
fos = r_fo.json().get('fulfillment_orders', [])
open_fos = []
for fo in fos:
    if fo.get('status') in ('open', 'in_progress'):
        fo_items = [{'id': li['id'], 'quantity': li.get('fulfillable_quantity', 0)}
                   for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
        if fo_items:
            open_fos.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_items})
if open_fos:
    payload = {'fulfillment': {'line_items_by_fulfillment_order': open_fos,
        'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
    r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
    if r_f.status_code in (200, 201):
        print(f'Shopify fulfillment created')
    else:
        print(f'Shopify FAIL: {r_f.status_code} {r_f.text[:200]}')
else:
    print('No open fulfillment orders')

print(f'\nDONE: {sol} | SO={new_so} DN={new_dn} AWB={awb} via {courier} | PPCOD COD={cod_amount}')
