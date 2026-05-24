import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r = requests.post(f'{BASE}/api/method/frappe.client.get_password',
                   headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

sol = 'SOL1202968'
dn = 'SHPDN27-10861'

# Atlas SO
r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
    params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',1]]),
            'fields': json.dumps(['name','shopify_order_id','custom_order_type','custom_cod_amount','custom_prepaid_amount','grand_total']),
            'limit_page_length': 1}, timeout=20)
so_d = r_so.json().get('data', [{}])[0]
print(f"=== ATLAS SO: {so_d.get('name','')} ===")
print(f"  custom_order_type: {so_d.get('custom_order_type','')}")
print(f"  custom_cod_amount: {so_d.get('custom_cod_amount',0)}")
print(f"  custom_prepaid_amount: {so_d.get('custom_prepaid_amount',0)}")
print(f"  grand_total: {so_d.get('grand_total',0)}")

shopify_oid = so_d.get('shopify_order_id', '')
if shopify_oid:
    r_shop = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    order = r_shop.json().get('order', {})
    print(f"\n=== SHOPIFY ORDER {shopify_oid} ===")
    print(f"  financial_status: {order.get('financial_status','')}")
    print(f"  total_price: {order.get('total_price','')}")
    print(f"  gateway: {order.get('payment_gateway_names','')}")

    r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
    txns = r_txn.json().get('transactions', [])
    print(f"\n  Transactions ({len(txns)}):")
    total_captured = 0
    for t in txns:
        kind = t.get('kind', '')
        status = t.get('status', '')
        amount = t.get('amount', '0')
        gateway = t.get('gateway', '')
        print(f"    {kind} | {status} | Rs {amount} | {gateway}")
        if kind in ('capture', 'sale') and status == 'success':
            total_captured = total_captured + float(amount)

    total_price = float(order.get('total_price', 0))
    cod_amount = total_price - total_captured
    print(f"\n  Total price: Rs {total_price}")
    print(f"  Total captured: Rs {total_captured}")
    print(f"  COD amount due: Rs {cod_amount}")

    # Check SO creation time vs transaction time
    so_created = so_d.get('creation', '')
    print(f"\n  SO created: {so_created if so_created else 'N/A'}")
    if txns:
        print(f"  Earliest txn: {txns[0].get('created_at','')}")
