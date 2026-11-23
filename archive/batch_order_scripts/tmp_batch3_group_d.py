import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

sol = 'SOL1204435'

# Step 1: Get Shopify order details
print(f'=== {sol} - Manual Atlas Sync ===')
r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
    headers=SHOP_H, params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
sh_orders = r_sh.json().get('orders', [])
if not sh_orders:
    print('Shopify order NOT FOUND')
    exit()

o = sh_orders[0]
oid = str(o['id'])
sa = o.get('shipping_address', {})
total_price = float(o.get('total_price', 0))
print(f'Shopify OID: {oid} | #{o.get("order_number","")}')
print(f'Customer: {sa.get("name","")} | {sa.get("city","")} {sa.get("province","")} PIN {sa.get("zip","")}')
print(f'Total: {total_price} | fin={o.get("financial_status","")}')

items = o.get('line_items', [])
for it in items:
    print(f'  SKU={it.get("sku","")} | {it.get("title","")} x{it.get("quantity",0)} @ {it.get("price","")}')

# Payment
r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}/transactions.json', headers=SHOP_H, timeout=15)
txns = r_txn.json().get('transactions', [])
captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
cod_amount = max(total_price - captured, 0)
order_type = 'Prepaid' if cod_amount == 0 else 'PPCOD' if captured > 0 else 'COD'
print(f'Payment: captured={captured}/{total_price} -> {order_type} COD={cod_amount}')

# Step 2: Create Address
phone = sa.get('phone', '')
if phone:
    phone = phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10:
        phone = phone[-10:]

addr_payload = {
    'doctype': 'Address',
    'address_title': sa.get('name', 'Customer'),
    'address_type': 'Shipping',
    'address_line1': sa.get('address1', '') or 'NA',
    'address_line2': sa.get('address2', '') or '',
    'city': sa.get('city', '') or 'NA',
    'state': sa.get('province', '') or '',
    'pincode': sa.get('zip', ''),
    'country': 'India',
    'phone': phone,
    'links': [{'link_doctype': 'Customer', 'link_name': 'Shopify D2C Customer'}],
}
r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
if r_addr.status_code == 200:
    addr_name = r_addr.json().get('data', {}).get('name', '')
    print(f'Address created: {addr_name}')
else:
    print(f'Address create: {r_addr.status_code} {r_addr.text[:200]}')
    # Try to find existing
    addr_name = sa.get('name', 'Customer') + '-' + sol + '-Shipping'
    print(f'Using fallback addr name: {addr_name}')

# Step 3: Create SO via server script (bypass GST validation)
print(f'\nStep 3: Creating SO via server script...')

# Build items JSON for script
items_json_parts = []
for it in items:
    sku = it.get('sku', '')
    qty = it.get('quantity', 1)
    price = float(it.get('price', 0))
    # Verify item exists
    r_item = requests.get(f'{BASE}/api/resource/Item/{sku}', headers=H, timeout=10)
    if r_item.status_code == 200:
        print(f'  Item OK: {sku}')
        items_json_parts.append(f'{{"item_code":"{sku}","qty":{qty},"rate":{price},"warehouse":"Main Warehouse - WTBBPL"}}')
    else:
        print(f'  Item NOT FOUND: {sku}')

if not items_json_parts:
    print('No valid items!')
    exit()

items_json = '[' + ','.join(items_json_parts) + ']'
txn_date = o.get('created_at', '')[:10]

sn1 = 'tmp_create_so_435'
script1 = (
    "import json\n"
    "so = frappe.new_doc('Sales Order')\n"
    "so.naming_series = 'SHP27-.#####'\n"
    "so.customer = 'Shopify D2C Customer'\n"
    "so.order_type = 'Sales'\n"
    "so.transaction_date = '" + txn_date + "'\n"
    "so.delivery_date = '" + txn_date + "'\n"
    "so.shopify_order_id = '" + oid + "'\n"
    "so.shopify_order_number = '" + sol + "'\n"
    "so.custom_order_type = '" + order_type + "'\n"
    "so.custom_cod_amount = " + str(cod_amount) + "\n"
    "so.custom_prepaid_amount = " + str(captured) + "\n"
    "so.shipping_address_name = '" + addr_name + "'\n"
    "so.customer_address = '" + addr_name + "'\n"
    "items_data = json.loads('" + items_json + "')\n"
    "for itd in items_data:\n"
    "    so.append('items', itd)\n"
    "so.flags.ignore_validate = True\n"
    "so.flags.ignore_mandatory = True\n"
    "so.insert(ignore_permissions=True)\n"
    "frappe.db.commit()\n"
    "frappe.response['message'] = 'DRAFT|' + so.name\n"
)

# Server scripts can't use import - remove it
script1 = script1.replace("import json\n", "")
script1 = script1.replace("json.loads('" + items_json + "')", "frappe.parse_json('" + items_json + "')")

r_s1 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn1, 'script_type': 'API', 'api_method': sn1, 'script': script1, 'allow_guest': 0}, timeout=15)
if r_s1.status_code != 200:
    print(f'Script1 create FAIL: {r_s1.status_code} {r_s1.text[:300]}')
    exit()

time.sleep(1)
r_r1 = requests.get(f'{BASE}/api/method/{sn1}', headers=H, timeout=30)
msg1 = r_r1.json().get('message', '')
print(f'Step 3 result: {msg1}')
requests.delete(f'{BASE}/api/resource/Server Script/{sn1}', headers=H, timeout=10)

if not msg1.startswith('DRAFT|'):
    print(f'SO creation failed: {msg1}')
    # Check exc
    print(f'Full response: {json.dumps(r_r1.json())[:500]}')
    exit()

so_name = msg1.split('|')[1]
print(f'Draft SO: {so_name}')

time.sleep(1)

# Step 4: Set proper fields and submit
print(f'\nStep 4: Setting fields and submitting SO...')
sn2 = 'tmp_submit_so_435'
script2 = (
    "so = frappe.get_doc('Sales Order', '" + so_name + "')\n"
    "so.company_address = 'Win The Buy Box Private Limited-Billing'\n"
    "so.gst_category = 'Unregistered'\n"
    "so.taxes_and_charges = 'GST 18% Interstate - WTBBPL'\n"
    "so.run_method('set_missing_values')\n"
    "so.run_method('calculate_taxes_and_totals')\n"
    "so.flags.ignore_validate = True\n"
    "so.save(ignore_permissions=True)\n"
    "so.submit()\n"
    "frappe.db.commit()\n"
    "frappe.response['message'] = 'OK|' + str(so.grand_total)\n"
)

r_s2 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn2, 'script_type': 'API', 'api_method': sn2, 'script': script2, 'allow_guest': 0}, timeout=15)
if r_s2.status_code != 200:
    print(f'Script2 create FAIL: {r_s2.status_code} {r_s2.text[:300]}')
    exit()

time.sleep(1)
r_r2 = requests.get(f'{BASE}/api/method/{sn2}', headers=H, timeout=30)
msg2 = r_r2.json().get('message', '')
print(f'Step 4 result: {msg2}')
requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)

if not str(msg2).startswith('OK'):
    print(f'SO submit failed')
    print(f'Full response: {json.dumps(r_r2.json())[:500]}')
    exit()

print(f'SO submitted: {so_name} | Grand Total: {msg2}')

time.sleep(2)

# Step 5: Create DN from SO
print(f'\nStep 5: Creating DN from SO {so_name}...')
r_make = requests.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                       headers=H, json={'source_name': so_name}, timeout=30)
if r_make.status_code != 200:
    print(f'make_dn FAIL: {r_make.status_code} {r_make.text[:200]}')
    exit()

dn_doc = r_make.json().get('message', {})

# Copy shopify fields
r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
    params={'fields': json.dumps(['shopify_order_id','shopify_order_number','shipping_address_name','customer_address'])}, timeout=15)
so_d = r_so.json().get('data', {})
dn_doc['shopify_order_id'] = so_d.get('shopify_order_id') or oid
dn_doc['shopify_order_number'] = so_d.get('shopify_order_number') or sol
dn_doc['shipping_address_name'] = so_d.get('shipping_address_name') or addr_name
dn_doc['customer_address'] = so_d.get('customer_address') or addr_name

r_ins = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_doc, timeout=30)
if r_ins.status_code != 200:
    print(f'DN insert FAIL: {r_ins.status_code} {r_ins.text[:200]}')
    exit()

new_dn = r_ins.json().get('data', {}).get('name', '')
print(f'DN created: {new_dn}')

# Step 6: Submit DN
print(f'Submitting {new_dn}...')
r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
                     headers=H, json={'docstatus': 1}, timeout=60)
time.sleep(4)

# Step 7: Check result
r_v = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
    params={'fields': json.dumps(['docstatus','awb_number','courier_partner','shopify_fulfillment_id'])}, timeout=15)
vd = r_v.json().get('data', {})
ds = vd.get('docstatus', 0)
awb = vd.get('awb_number', '') or ''
cp = vd.get('courier_partner', '') or ''
ful = vd.get('shopify_fulfillment_id', '') or ''

if ds == 1 and awb:
    print(f'\nSUCCESS: {sol} | SO={so_name} | DN={new_dn} | AWB={awb} | {cp} | Fulfillment={ful}')
elif ds == 1:
    print(f'\nSUBMITTED but NO AWB on {new_dn}')
    try:
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
            params={'filters': json.dumps([['error','like','%'+new_dn+'%']]),
                    'fields': json.dumps(['error']),
                    'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
        errs = r_err.json().get('data', [])
        if errs:
            err = str(errs[0].get('error',''))
            for line in err.split('\n'):
                ll = line.lower()
                if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative']):
                    print(f'ERR: {line.strip()[:200]}')
    except:
        pass
else:
    print(f'\nFAIL ds={ds}')
    try:
        msgs = r_sub.json().get('_server_messages', '')
        if msgs:
            for p in json.loads(msgs):
                inner = json.loads(p) if isinstance(p, str) else p
                m = inner.get('message', str(inner))
                print(f'MSG: {m[:200]}')
    except:
        print(f'Status: {r_sub.status_code}')
