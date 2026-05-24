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

orders = ['SOL1204809','SOL1204919','SOL1205015','SOL1205022','SOL1205080']

for sol in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} ===')

    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
        headers=SHOP_H, params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
    sh_orders = r_sh.json().get('orders', [])
    if not sh_orders:
        print(f'  NOT FOUND on Shopify!')
        continue

    o = sh_orders[0]
    shopify_oid = o.get('id', '')
    sa = o.get('shipping_address', {}) or {}
    ba = o.get('billing_address', {}) or {}
    fin = o.get('financial_status', '')
    gw = ', '.join(o.get('payment_gateway_names', []))
    total = o.get('total_price', '')
    subtotal = o.get('subtotal_price', '')
    tax = o.get('total_tax', '')
    email = o.get('email', '')
    created = o.get('created_at', '')

    print(f'  Shopify ID: {shopify_oid} | Created: {created}')
    print(f'  Financial: {fin} | Gateway: {gw} | Total: {total} | Subtotal: {subtotal} | Tax: {tax}')
    print(f'  Email: {email}')

    # Shipping address
    print(f'  Ship To: {sa.get("name","")}')
    print(f'    {sa.get("address1","")}')
    print(f'    {sa.get("address2","")}')
    print(f'    {sa.get("city","")} {sa.get("province","")} {sa.get("zip","")}')
    print(f'    Phone: {sa.get("phone","")}')

    # Items
    print(f'  Items:')
    for li in o.get('line_items', []):
        sku = li.get('sku', '')
        title = li.get('title', '')
        variant = li.get('variant_title', '')
        qty = li.get('quantity', 0)
        price = li.get('price', '')
        discount = li.get('total_discount', '0.00')
        taxable = li.get('taxable', False)
        tax_lines = li.get('tax_lines', [])
        tax_amt = sum(float(t.get('price','0')) for t in tax_lines)
        print(f'    SKU={sku} | "{title}" {variant} | qty={qty} | price={price} | discount={discount} | tax={tax_amt}')

    # Transactions
    r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
    txns = r_txn.json().get('transactions', [])
    captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
    print(f'  Transactions (captured={captured}):')
    for t in txns:
        print(f'    {t.get("gateway","")}/{t.get("kind","")} Rs{t.get("amount","")} status={t.get("status","")}')

    # Determine order type
    if fin == 'paid':
        otype = 'Prepaid'
        cod_val = 0
    elif fin == 'partially_paid':
        otype = 'PPCOD'
        cod_val = round(float(total) - captured, 2)
    else:
        otype = 'COD'
        cod_val = float(total)
    print(f'  => Type: {otype} | COD amount: {cod_val}')

    # Check serviceability
    pin = sa.get('zip', '')
    ot_cp = 'COD' if otype in ('PPCOD', 'COD') else 'PREPAID'
    cv = cod_val if ot_cp == 'COD' else 0
    payload_svc = [{'pickup_pincode': '501218', 'drop_pincode': pin, 'order_type': ot_cp,
                    'cod_value': cv, 'delivery_type': 'FORWARD', 'item': 'DGS',
                    'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': max(float(total),1)}]
    r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
        json=payload_svc, headers={'Content-Type': 'application/json'}, timeout=10)
    svc = r_svc.json()
    if svc.get('meta', {}).get('success') and svc.get('result', [{}])[0].get('preference_array'):
        couriers = [c.get('courier_name','') for c in svc['result'][0]['preference_array']]
        print(f'  Serviceable ({ot_cp}): {", ".join(couriers)}')
    else:
        print(f'  NOT SERVICEABLE ({ot_cp})')

    # Check if SKU exists on Atlas
    print(f'  Atlas SKU check:')
    for li in o.get('line_items', []):
        sku = li.get('sku', '')
        if sku:
            r_item = requests.get(f'{BASE}/api/resource/Item/{sku}', headers=H, timeout=10)
            if r_item.status_code == 200:
                it = r_item.json().get('data', {})
                print(f'    {sku}: EXISTS | is_stock={it.get("is_stock_item",0)} | rate={it.get("valuation_rate",0)}')
            else:
                print(f'    {sku}: NOT FOUND')

    # Check duplicate (SOL1205015 vs SOL1205022)
    if sol in ('SOL1205015', 'SOL1205022'):
        print(f'  *** POSSIBLE DUPLICATE - same customer SAVIO SUNDAR, same SKU SOL-AF-124 ***')

    time.sleep(0.5)
