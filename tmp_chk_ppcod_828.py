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

sol = 'SOL1202828'
dn = 'SHPDN27-10845'

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

# Atlas DN
r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
    params={'fields': json.dumps(['grand_total','custom_prepaid_amount','custom_cod_amount','awb_number','courier_partner'])}, timeout=20)
dn_d = r_dn.json().get('data', {})
print(f"\n=== ATLAS DN: {dn} ===")
print(f"  grand_total: {dn_d.get('grand_total',0)}")
print(f"  custom_prepaid_amount: {dn_d.get('custom_prepaid_amount','N/A')}")
print(f"  custom_cod_amount: {dn_d.get('custom_cod_amount','N/A')}")
print(f"  awb: {dn_d.get('awb_number','')}")
print(f"  courier: {dn_d.get('courier_partner','')}")

# Shopify order details
shopify_oid = so_d.get('shopify_order_id', '')
if shopify_oid:
    r_shop = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    order = r_shop.json().get('order', {})
    print(f"\n=== SHOPIFY ORDER {shopify_oid} ===")
    print(f"  financial_status: {order.get('financial_status','')}")
    print(f"  total_price: {order.get('total_price','')}")
    print(f"  gateway: {order.get('payment_gateway_names','')}")

    # Transactions
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
    print(f"  Total captured (prepaid): Rs {total_captured}")
    print(f"  COD amount due: Rs {cod_amount}")

# Check Clickpost order details
print(f"\n=== CLICKPOST ORDER ===")
awb = dn_d.get('awb_number', '')
if awb:
    r_cp = requests.get(f'https://www.clickpost.in/api/v1/tracking/?username=solara&key=d3464616-bbd6-4874-919a-a7e8bd14d66f&waybill={awb}',
                        timeout=15)
    try:
        cp = r_cp.json()
        if cp.get('meta', {}).get('success'):
            result = cp.get('result', {})
            print(f"  order_type: {result.get('order_type','')}")
            print(f"  cod_value: {result.get('cod_value','')}")
            print(f"  invoice_value: {result.get('invoice_value','')}")
            print(f"  status: {result.get('latest_status',{}).get('clickpost_status_description','')}")
        else:
            print(f"  Tracking API: {cp.get('meta',{}).get('message','')}")
    except:
        print(f"  Clickpost response error")
