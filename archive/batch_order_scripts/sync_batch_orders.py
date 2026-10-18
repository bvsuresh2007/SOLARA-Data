import requests, json, sys, time
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

order_ids = [
    'SOL1192986', 'SOL1192993', 'SOL1192996', 'SOL1193004',
    'SOL1193021', 'SOL1193025', 'SOL1193060', 'SOL1193089',
    'SOL1193218', 'SOL1193271', 'SOL1193333', 'SOL1193369',
    'SOL1193375', 'SOL1193438', 'SOL1193462', 'SOL1193463',
    'SOL1193471', 'SOL1193488',
]

results = []

for idx, oid in enumerate(order_ids, 1):
    print(f'\n[{idx}/{len(order_ids)}] {oid}', flush=True)

    try:
        # Check if already in Atlas
        rc = s.get(f'{BASE}/api/resource/Sales Order', params={
            'filters': json.dumps([['custom_shopify_order_number', '=', oid]]),
            'fields': json.dumps(['name', 'status', 'docstatus']),
            'limit_page_length': 5
        }, timeout=15)
        existing_sos = rc.json().get('data', [])
        if existing_sos:
            best = max(existing_sos, key=lambda x: ({1: 3, 0: 2, 2: 1}.get(x['docstatus'], 0)))
            ds = {0: 'Draft', 1: 'Submitted', 2: 'Cancelled'}
            print(f'  Already in Atlas: {best["name"]} | {ds.get(best["docstatus"], "")}', flush=True)
            results.append((oid, 'EXISTS', best['name'], '', ds.get(best['docstatus'], ''), ''))
            continue

        # Lookup on Shopify
        r1 = shopify_s.get(f'https://{shop_url}/admin/api/2024-01/orders.json', params={
            'name': oid, 'status': 'any', 'limit': 5
        }, timeout=15)
        shop_orders = r1.json().get('orders', [])
        if not shop_orders:
            print(f'  NOT FOUND ON SHOPIFY', flush=True)
            results.append((oid, 'NOT_FOUND', '', '', '', 'Not on Shopify'))
            continue

        o = shop_orders[0]
        cust = o.get('customer', {})
        ship = o.get('shipping_address', {}) or o.get('billing_address', {}) or {}
        cust_name = f'{cust.get("first_name", "")} {cust.get("last_name", "")}'.strip()
        if not cust_name:
            cust_name = ship.get('name', '') or f'Shopify Customer {oid}'
        state = ship.get('province', '')
        shopify_id = str(o['id'])

        items_desc = ', '.join([f'{li["sku"]} x{li["quantity"]}' for li in o.get('line_items', [])])
        print(f'  Shopify: {o["financial_status"]} | {cust_name} | {ship.get("city","")}, {state} | {o["total_price"]} INR', flush=True)
        print(f'  Items: {items_desc}', flush=True)

        # Stock check
        all_ok = True
        stock_issues = []
        for li in o.get('line_items', []):
            sku = li['sku']
            qty_needed = li['quantity']
            ri = s.get(f'{BASE}/api/resource/Item/{sku}', params={
                'fields': json.dumps(['name', 'is_stock_item'])
            }, timeout=15)
            if ri.status_code != 200:
                stock_issues.append(f'{sku}: NOT IN ATLAS')
                all_ok = False
                continue
            idata = ri.json()['data']
            if not idata['is_stock_item']:
                rb = s.get(f'{BASE}/api/resource/Product Bundle/{sku}', timeout=15)
                if rb.status_code == 200:
                    for comp in rb.json()['data'].get('items', []):
                        rs2 = s.get(f'{BASE}/api/method/erpnext.stock.utils.get_stock_balance', params={
                            'item_code': comp['item_code'], 'warehouse': 'Main Warehouse - WTBBPL'
                        }, timeout=15)
                        stock = float(rs2.json().get('message', 0))
                        needed = comp['qty'] * qty_needed
                        if stock < needed:
                            all_ok = False
                            stock_issues.append(f'{comp["item_code"]}: {stock}/{needed}')
            else:
                rs2 = s.get(f'{BASE}/api/method/erpnext.stock.utils.get_stock_balance', params={
                    'item_code': sku, 'warehouse': 'Main Warehouse - WTBBPL'
                }, timeout=15)
                stock = float(rs2.json().get('message', 0))
                if stock < qty_needed:
                    all_ok = False
                    stock_issues.append(f'{sku}: {stock}/{qty_needed}')

        stock_str = 'OK' if all_ok else f'LOW: {"; ".join(stock_issues)}'
        print(f'  Stock: {stock_str}', flush=True)

        # Create Customer if not exists
        rc2 = s.get(f'{BASE}/api/resource/Customer', params={
            'filters': json.dumps([['customer_name', '=', cust_name]]),
            'fields': json.dumps(['name']),
            'limit_page_length': 1
        }, timeout=15)
        existing_custs = rc2.json().get('data', [])
        if existing_custs:
            cust_id = existing_custs[0]['name']
        else:
            rc3 = s.post(f'{BASE}/api/resource/Customer', json={
                'doctype': 'Customer', 'customer_name': cust_name,
                'customer_type': 'Individual', 'customer_group': 'Individual',
                'territory': 'All Territories',
            }, timeout=15)
            if rc3.status_code != 200:
                print(f'  Customer create FAILED', flush=True)
                results.append((oid, 'FAILED', '', '', '', 'Customer create failed'))
                continue
            cust_id = rc3.json()['data']['name']

        # Create Address if not exists
        addr_name = f'{cust_name}-Shipping'
        ra = s.get(f'{BASE}/api/resource/Address/{addr_name}', timeout=10)
        if ra.status_code != 200:
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
            else:
                addr_name = None

        # Tax template
        is_telangana = state.lower().strip() == 'telangana'
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
            err = rs.text[:200]
            print(f'  SO create FAILED: {err}', flush=True)
            results.append((oid, 'FAILED', '', '', '', err[:80]))
            continue

        so_name = rs.json()['data']['name']
        grand_total = rs.json()['data']['grand_total']

        rs2 = s.put(f'{BASE}/api/resource/Sales Order/{so_name}', json={'docstatus': 1}, timeout=30)
        if rs2.status_code != 200:
            print(f'  SO created {so_name} but submit FAILED', flush=True)
            results.append((oid, 'DRAFT', so_name, str(grand_total), 'Submit failed', stock_str))
            continue

        print(f'  SO: {so_name} | Total: {grand_total} | Submitted', flush=True)
        results.append((oid, 'SYNCED', so_name, str(grand_total), 'Submitted', stock_str))

    except Exception as e:
        print(f'  ERROR: {e}', flush=True)
        results.append((oid, 'ERROR', '', '', '', str(e)[:80]))

    time.sleep(0.3)

# Summary
print(f'\n{"="*100}')
print(f'{"Order":<14} {"Status":<10} {"SO":<14} {"Total":>8} {"SO Status":<12} {"Stock"}')
print(f'{"="*100}')
for oid, status, so, total, so_status, stock in results:
    print(f'{oid:<14} {status:<10} {so:<14} {total:>8} {so_status:<12} {stock}')

synced = sum(1 for r in results if r[1] == 'SYNCED')
exists = sum(1 for r in results if r[1] == 'EXISTS')
failed = sum(1 for r in results if r[1] in ('FAILED', 'ERROR', 'NOT_FOUND'))
print(f'\nSynced: {synced} | Already existed: {exists} | Failed: {failed} | Total: {len(results)}')
