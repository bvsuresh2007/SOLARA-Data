import requests, json, sys
from dotenv import dotenv_values

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

# Get Shopify creds
r = s.get(f'{BASE}/api/resource/Shopify Setting/Shopify Setting', timeout=15)
data = r.json()['data']
shop_url = data['shopify_url']
shop_token = data['password']
shopify_s = requests.Session()
shopify_s.headers.update({'X-Shopify-Access-Token': shop_token, 'Content-Type': 'application/json'})

oid = sys.argv[1] if len(sys.argv) > 1 else 'SOL1193037'

# Lookup on Shopify
r1 = shopify_s.get(f'https://{shop_url}/admin/api/2024-01/orders.json', params={
    'name': oid, 'status': 'any', 'limit': 5
}, timeout=15)
shop_orders = r1.json().get('orders', [])
if not shop_orders:
    print('NOT FOUND ON SHOPIFY')
    sys.exit(1)

o = shop_orders[0]
cust = o.get('customer', {})
ship = o.get('shipping_address', {}) or {}
cust_name = f'{cust.get("first_name", "")} {cust.get("last_name", "")}'.strip()
if not cust_name:
    cust_name = ship.get('name', '') or f'Shopify Customer {oid}'
state = ship.get('province', '')
shopify_id = str(o['id'])

print(f'Order: {o["name"]} | Shopify ID: {shopify_id}')
print(f'Created: {o["created_at"]}')
print(f'Financial: {o["financial_status"]} | Fulfillment: {o.get("fulfillment_status", "unfulfilled")}')
print(f'Customer: {cust_name} | {ship.get("city", "")}, {state} {ship.get("zip", "")}')
print(f'Subtotal: {o["subtotal_price"]} | Discount: {o.get("total_discounts", "0")} | Total: {o["total_price"]}')
print(f'Items:')
for li in o.get('line_items', []):
    print(f'  {li["sku"]} x{li["quantity"]} @ {li["price"]} ({li["title"]})')

# Stock check
print(f'\n--- Stock Check ---')
all_ok = True
for li in o.get('line_items', []):
    sku = li['sku']
    qty_needed = li['quantity']
    ri = s.get(f'{BASE}/api/resource/Item/{sku}', params={
        'fields': json.dumps(['name', 'item_name', 'is_stock_item', 'item_group'])
    }, timeout=15)
    if ri.status_code != 200:
        print(f'{sku}: NOT IN ATLAS')
        all_ok = False
        continue
    idata = ri.json()['data']
    if not idata['is_stock_item']:
        rb = s.get(f'{BASE}/api/resource/Product Bundle/{sku}', timeout=15)
        if rb.status_code == 200:
            print(f'{sku}: BUNDLE')
            for comp in rb.json()['data'].get('items', []):
                rs2 = s.get(f'{BASE}/api/method/erpnext.stock.utils.get_stock_balance', params={
                    'item_code': comp['item_code'], 'warehouse': 'Main Warehouse - WTBBPL'
                }, timeout=15)
                stock = float(rs2.json().get('message', 0))
                needed = comp['qty'] * qty_needed
                ok = 'OK' if stock >= needed else 'LOW'
                if ok == 'LOW':
                    all_ok = False
                print(f'  {comp["item_code"]} x{comp["qty"]} | Stock: {stock} | Need: {needed} [{ok}]')
        else:
            print(f'{sku}: non-stock, not bundle - OK')
    else:
        rs2 = s.get(f'{BASE}/api/method/erpnext.stock.utils.get_stock_balance', params={
            'item_code': sku, 'warehouse': 'Main Warehouse - WTBBPL'
        }, timeout=15)
        stock = float(rs2.json().get('message', 0))
        ok = 'OK' if stock >= qty_needed else 'LOW'
        if ok == 'LOW':
            all_ok = False
        print(f'{sku}: Stock: {stock} | Need: {qty_needed} [{ok}]')

# Create Customer
print(f'\n--- Creating SO ---')
rc = s.get(f'{BASE}/api/resource/Customer', params={
    'filters': json.dumps([['customer_name', '=', cust_name]]),
    'fields': json.dumps(['name']),
    'limit_page_length': 1
}, timeout=15)
existing = rc.json().get('data', [])
if existing:
    cust_id = existing[0]['name']
    print(f'Customer exists: {cust_id}')
else:
    rc2 = s.post(f'{BASE}/api/resource/Customer', json={
        'doctype': 'Customer', 'customer_name': cust_name,
        'customer_type': 'Individual', 'customer_group': 'Individual',
        'territory': 'All Territories',
    }, timeout=15)
    cust_id = rc2.json()['data']['name']
    print(f'Customer created: {cust_id}')

# Create Address
addr_name = f'{cust_name}-Shipping'
ra = s.get(f'{BASE}/api/resource/Address/{addr_name}', timeout=10)
if ra.status_code == 200:
    print(f'Address exists: {addr_name}')
else:
    addr1 = (ship.get('address1', '') or 'N/A')[:140]
    ra2 = s.post(f'{BASE}/api/resource/Address', json={
        'doctype': 'Address', 'address_title': cust_name, 'address_type': 'Shipping',
        'address_line1': addr1, 'address_line2': ship.get('address2', '') or '',
        'city': ship.get('city', '') or 'N/A', 'state': state,
        'pincode': ship.get('zip', '') or '', 'country': 'India',
        'phone': ship.get('phone', '') or '', 'email_id': cust.get('email', '') or '',
        'is_shipping_address': 1, 'is_primary_address': 1,
        'links': [{'link_doctype': 'Customer', 'link_name': cust_id}]
    }, timeout=15)
    if ra2.status_code == 200:
        addr_name = ra2.json()['data']['name']
        print(f'Address created: {addr_name}')
    else:
        print(f'Address failed: {ra2.text[:150]}')
        addr_name = None

# Determine tax template
is_telangana = state.lower().strip() in ['telangana']
tax_template = 'GST 18% Intrastate - WTBBPL' if is_telangana else 'GST 18% Interstate - WTBBPL'

items = []
for li in o.get('line_items', []):
    items.append({
        'item_code': li['sku'], 'qty': li['quantity'], 'rate': float(li['price']),
        'warehouse': 'Main Warehouse - WTBBPL', 'delivery_date': '2026-04-05',
    })

discount = float(o.get('total_discounts', '0'))

so_data = {
    'doctype': 'Sales Order', 'customer': cust_id,
    'company': 'Win The Buy Box Private Limited', 'order_type': 'Sales',
    'currency': 'INR', 'conversion_rate': 1.0,
    'selling_price_list': 'Ecommerce Integrations - Ignore',
    'price_list_currency': 'INR',
    'transaction_date': o['created_at'][:10], 'delivery_date': '2026-04-05',
    'shopify_order_id': shopify_id, 'custom_shopify_order_number': oid,
    'territory': 'All Territories', 'tax_category': 'Ecommerce Integrations - Ignore',
    'taxes_and_charges': tax_template,
    'apply_discount_on': 'Grand Total', 'discount_amount': discount,
    'items': items,
}
if addr_name:
    so_data['shipping_address_name'] = addr_name
    so_data['customer_address'] = addr_name

rs = s.post(f'{BASE}/api/resource/Sales Order', json=so_data, timeout=30)
if rs.status_code != 200:
    print(f'SO create FAILED: {rs.text[:300]}')
    sys.exit(1)

so_name = rs.json()['data']['name']
grand_total = rs.json()['data']['grand_total']
print(f'SO created: {so_name} (total: {grand_total})')

rs2 = s.put(f'{BASE}/api/resource/Sales Order/{so_name}', json={'docstatus': 1}, timeout=30)
if rs2.status_code != 200:
    print(f'SO submit FAILED: {rs2.text[:300]}')
else:
    print(f'SO submitted: {rs2.json()["data"]["status"]}')

print(f'\nStock OK for DN: {all_ok}')
