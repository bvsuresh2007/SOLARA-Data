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

sol = 'SOL1203882'
oid = '7059620757736'

# Get Shopify order
r = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}.json', headers=SHOP_H, timeout=15)
order = r.json().get('order', {})
sa = order.get('shipping_address', {})
total_price = float(order.get('total_price', 0))
print(f'Shopify: {sol} | Rs {total_price}')
print(f'Ship to: {sa.get("name","")} | {sa.get("city","")} {sa.get("province","")} PIN {sa.get("zip","")}')

items = order.get('line_items', [])
for it in items:
    print(f'  SKU={it.get("sku","")} | {it.get("title","")} x{it.get("quantity",0)} @ {it.get("price","")}')

# Payment info
r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}/transactions.json', headers=SHOP_H, timeout=15)
txns = r_txn.json().get('transactions', [])
total_captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
cod_amount = max(total_price - total_captured, 0)
order_type = 'Prepaid' if cod_amount == 0 else 'PPCOD' if total_captured > 0 else 'COD'
print(f'Payment: captured={total_captured}/{total_price} → {order_type} COD={cod_amount}')

# Step 1: Create Address from Shopify shipping_address
addr_name = f'{sa.get("name","Customer")}-{sol}-Shipping'
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
    addr_name = r_addr.json().get('data', {}).get('name', addr_name)
    print(f'Address created: {addr_name}')
elif r_addr.status_code == 409:
    # Already exists
    print(f'Address already exists, using: {addr_name}')
else:
    print(f'Address create fail: {r_addr.status_code} {r_addr.text[:200]}')

# Step 2: Map SKUs to ERPNext item_codes
so_items = []
for it in items:
    sku = it.get('sku', '')
    qty = it.get('quantity', 1)
    price = float(it.get('price', 0))

    # Check if item exists
    r_item = requests.get(f'{BASE}/api/resource/Item/{sku}', headers=H, timeout=10)
    if r_item.status_code == 200:
        so_items.append({
            'item_code': sku,
            'qty': qty,
            'rate': price,
            'warehouse': 'Main Warehouse - WTBBPL',
        })
        print(f'  Item OK: {sku}')
    else:
        print(f'  Item NOT FOUND: {sku}')

if not so_items:
    print('No valid items, aborting')
    exit()

# Step 3: Create SO
so_payload = {
    'doctype': 'Sales Order',
    'naming_series': 'SHP27-.#####',
    'customer': 'Shopify D2C Customer',
    'order_type': 'Sales',
    'transaction_date': order.get('created_at', '')[:10],
    'delivery_date': order.get('created_at', '')[:10],
    'shopify_order_id': str(oid),
    'shopify_order_number': sol,
    'custom_order_type': order_type,
    'custom_cod_amount': cod_amount,
    'custom_prepaid_amount': total_captured,
    'shipping_address_name': addr_name,
    'customer_address': addr_name,
    'items': so_items,
    'taxes_and_charges': 'Output GST Out-State - WTBBPL',
}

r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
if r_so.status_code != 200:
    print(f'SO create fail: {r_so.status_code} {r_so.text[:400]}')
    exit()

so_name = r_so.json().get('data', {}).get('name', '')
print(f'SO created: {so_name}')

# Step 4: Submit SO
r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
if r_sub.status_code == 200:
    print(f'SO submitted: {so_name}')
else:
    print(f'SO submit fail: {r_sub.status_code} {r_sub.text[:400]}')
    # Check if it's a server message we can parse
    try:
        msgs = json.loads(r_sub.json().get('_server_messages', '[]'))
        for m in msgs:
            inner = json.loads(m) if isinstance(m, str) else m
            print(f'  MSG: {inner.get("message","")[:200]}')
    except:
        pass

time.sleep(2)

# Verify
r_v = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H,
    params={'fields': json.dumps(['docstatus','grand_total','shopify_order_id','shopify_order_number','shipping_address_name'])}, timeout=15)
vd = r_v.json().get('data', {})
print(f'Verified: ds={vd.get("docstatus",0)} | total={vd.get("grand_total","")} | ship={vd.get("shipping_address_name","")}')
