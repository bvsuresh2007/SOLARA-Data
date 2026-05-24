import requests, json, time
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

shopify = requests.Session()
shopify.headers.update({
    'X-Shopify-Access-Token': shop_token,
    'Content-Type': 'application/json'
})

order_ids = [
    ('SOL1194344', '7000201461992'),
    ('SOL1194331', '7000124227816'),
    ('SOL1194318', '7000030347496'),
    ('SOL1194310', '6999997219048'),
    ('SOL1194299', '6999955079400'),
    ('SOL1194292', '6999926997224'),
    ('SOL1194277', '6999855694056'),
    ('SOL1194274', '6999853138152'),
]

results = []

for idx, (oid, shopify_id) in enumerate(order_ids, 1):
    print(f'\n[{idx}/8] {oid} (Shopify {shopify_id})', flush=True)

    try:
        # Fetch full order from Shopify
        r1 = shopify.get(f'https://{shop_url}/admin/api/2024-01/orders/{shopify_id}.json', timeout=15)
        order = r1.json()['order']

        cust = order.get('customer', {})
        cust_name = f'{cust.get("first_name", "")} {cust.get("last_name", "")}'.strip()
        if not cust_name:
            cust_name = order.get('shipping_address', {}).get('name', '') or f'Shopify Customer {oid}'
        ship = order.get('shipping_address', {}) or order.get('billing_address', {}) or {}

        # Create Customer if not exists
        rc = s.get(f'{BASE}/api/resource/Customer', params={
            'filters': json.dumps([['customer_name', '=', cust_name]]),
            'fields': json.dumps(['name']),
            'limit_page_length': 1
        }, timeout=15)
        existing_custs = rc.json().get('data', [])

        if existing_custs:
            cust_id = existing_custs[0]['name']
            print(f'  Customer exists: {cust_id}', flush=True)
        else:
            rc2 = s.post(f'{BASE}/api/resource/Customer', json={
                'doctype': 'Customer',
                'customer_name': cust_name,
                'customer_type': 'Individual',
                'customer_group': 'Individual',
                'territory': 'All Territories',
            }, timeout=15)
            if rc2.status_code == 200:
                cust_id = rc2.json()['data']['name']
                print(f'  Customer created: {cust_id}', flush=True)
            else:
                print(f'  Customer create FAILED: {rc2.text[:150]}', flush=True)
                results.append((oid, 'FAILED', '', '', 'Customer create failed'))
                continue

        # Create Address if not exists
        addr_name = f'{cust_name}-Shipping'
        ra = s.get(f'{BASE}/api/resource/Address/{addr_name}', timeout=10)
        if ra.status_code == 200:
            print(f'  Address exists: {addr_name}', flush=True)
        else:
            addr_data = {
                'doctype': 'Address',
                'address_title': cust_name,
                'address_type': 'Shipping',
                'address_line1': ship.get('address1', '') or 'N/A',
                'address_line2': ship.get('address2', '') or '',
                'city': ship.get('city', '') or 'N/A',
                'state': ship.get('province', '') or '',
                'pincode': ship.get('zip', '') or '',
                'country': 'India',
                'phone': ship.get('phone', '') or '',
                'email_id': cust.get('email', '') or '',
                'is_shipping_address': 1,
                'is_primary_address': 1,
                'links': [{'link_doctype': 'Customer', 'link_name': cust_id}]
            }
            ra2 = s.post(f'{BASE}/api/resource/Address', json=addr_data, timeout=15)
            if ra2.status_code == 200:
                addr_name = ra2.json()['data']['name']
                print(f'  Address created: {addr_name}', flush=True)
            else:
                print(f'  Address create FAILED: {ra2.text[:150]}', flush=True)
                addr_name = None

        # Build SO items
        items = []
        for li in order.get('line_items', []):
            items.append({
                'item_code': li['sku'],
                'qty': li['quantity'],
                'rate': float(li['price']),
                'warehouse': 'Main Warehouse - WTBBPL',
                'delivery_date': '2026-04-05',
            })

        discount = float(order.get('total_discounts', '0'))

        so_data = {
            'doctype': 'Sales Order',
            'customer': cust_id,
            'company': 'Win The Buy Box Private Limited',
            'order_type': 'Sales',
            'currency': 'INR',
            'conversion_rate': 1.0,
            'selling_price_list': 'Ecommerce Integrations - Ignore',
            'price_list_currency': 'INR',
            'transaction_date': order['created_at'][:10],
            'delivery_date': '2026-04-05',
            'shopify_order_id': str(shopify_id),
            'custom_shopify_order_number': oid,
            'territory': 'All Territories',
            'tax_category': 'Ecommerce Integrations - Ignore',
            'taxes_and_charges': 'GST 18% Interstate - WTBBPL',
            'apply_discount_on': 'Grand Total',
            'discount_amount': discount,
            'items': items,
        }
        if addr_name:
            so_data['shipping_address_name'] = addr_name
            so_data['customer_address'] = addr_name

        # Create SO
        rs = s.post(f'{BASE}/api/resource/Sales Order', json=so_data, timeout=30)
        if rs.status_code != 200:
            print(f'  SO create FAILED: {rs.text[:200]}', flush=True)
            results.append((oid, 'FAILED', '', '', f'SO create: {rs.text[:100]}'))
            continue

        so_name = rs.json()['data']['name']
        grand_total = rs.json()['data']['grand_total']
        print(f'  SO created: {so_name} (total: {grand_total})', flush=True)

        # Submit SO
        rs2 = s.put(f'{BASE}/api/resource/Sales Order/{so_name}', json={'docstatus': 1}, timeout=30)
        if rs2.status_code != 200:
            print(f'  SO submit FAILED: {rs2.text[:200]}', flush=True)
            results.append((oid, 'FAILED', so_name, '', f'SO submit: {rs2.text[:100]}'))
            continue
        print(f'  SO submitted', flush=True)

        # Create DN from SO
        rd1 = s.post(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                      json={'source_name': so_name}, timeout=30)
        if rd1.status_code != 200:
            print(f'  Make DN FAILED: {rd1.status_code}', flush=True)
            results.append((oid, 'SO only', so_name, '', 'make_dn failed'))
            continue

        dn_data = rd1.json().get('message', {})
        dn_data['shopify_order_id'] = str(shopify_id)
        dn_data['shopify_order_number'] = oid

        # Save DN
        rd2 = s.post(f'{BASE}/api/resource/Delivery Note', json=dn_data, timeout=30)
        if rd2.status_code != 200:
            print(f'  DN save FAILED: {rd2.text[:150]}', flush=True)
            results.append((oid, 'SO only', so_name, '', f'DN save: {rd2.text[:80]}'))
            continue

        dn_name = rd2.json()['data']['name']

        # Submit DN
        rd3 = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={'docstatus': 1}, timeout=30)
        if rd3.status_code != 200:
            print(f'  DN submit FAILED: {rd3.text[:150]}', flush=True)
            results.append((oid, 'DN draft', so_name, dn_name, f'DN submit: {rd3.text[:80]}'))
            continue

        print(f'  DN submitted: {dn_name}', flush=True)

        # Check AWB
        time.sleep(3)
        rd4 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner', 'shipment_status'])
        }, timeout=15)
        d4 = rd4.json()['data']
        awb = d4.get('awb_number', '') or ''

        if not awb:
            time.sleep(7)
            rd4 = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner', 'shipment_status'])
            }, timeout=15)
            d4 = rd4.json()['data']
            awb = d4.get('awb_number', '') or ''

        courier = d4.get('courier_partner', '') or ''
        ship_status = d4.get('shipment_status', '') or ''

        if awb:
            print(f'  AWB: {awb} | {courier}', flush=True)
            results.append((oid, 'SUCCESS', so_name, dn_name, awb))
        else:
            print(f'  No AWB yet ({ship_status})', flush=True)
            results.append((oid, 'NO AWB', so_name, dn_name, ship_status))

    except Exception as e:
        print(f'  ERROR: {e}', flush=True)
        results.append((oid, 'ERROR', '', '', str(e)[:100]))

    time.sleep(0.5)

# Summary
print(f'\n{"="*70}')
print(f'RESULTS')
print(f'{"="*70}')
for oid, status, so, dn, detail in results:
    print(f'{oid} | {status} | SO: {so} | DN: {dn} | {detail}')

awb_count = sum(1 for r in results if r[1] == 'SUCCESS')
print(f'\nAWBs obtained: {awb_count}/8')
