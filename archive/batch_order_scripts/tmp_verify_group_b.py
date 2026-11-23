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

orders = [
    ('SOL1204747', 'SHPDN27-13885', '29044411211475', 4),
    ('SOL1204873', 'SHPDN27-13886', '29044411211486', 4),
    ('SOL1204894', 'SHPDN27-13887', '29044411211490', 4),
    ('SOL1204918', 'SHPDN27-13888', '29044411211501', 4),
    ('SOL1205054', 'SHPDN27-13889', '29044411211512', 4),
]

for sol, dn, awb, cp_id in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | DN={dn} | AWB={awb} ===')

    # Atlas DN
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    d = r_dn.json().get('data', {})
    print(f'  ATLAS DN: ds={d.get("docstatus")} | awb={d.get("awb_number","")} | courier={d.get("courier_partner","")}')
    print(f'  Customer: {d.get("customer_name","")} | Total: {d.get("grand_total",0)}')
    addr = d.get('shipping_address_name', '')
    print(f'  Ship addr: {addr}')
    items = d.get('items', [])
    skus = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",1))}' for it in items])
    print(f'  Items: {skus}')

    # Atlas SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','custom_order_type','custom_cod_amount','grand_total','shopify_order_id']),
                'limit_page_length': 1}, timeout=15)
    so = r_so.json().get('data', [{}])[0]
    shopify_oid = so.get('shopify_order_id', '')
    print(f'  ATLAS SO: {so.get("name","")} | type={so.get("custom_order_type","")} | COD={so.get("custom_cod_amount",0)}')

    # Shopify
    if shopify_oid:
        r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh = r_ord.json().get('order', {})
        fin = sh.get('financial_status', '')
        gw = ', '.join(sh.get('payment_gateway_names', []))
        ful_status = sh.get('fulfillment_status', '')

        r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
        txns = r_txn.json().get('transactions', [])
        captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
        txn_details = []
        for t in txns:
            if t.get('status') == 'success':
                txn_details.append(f'{t.get("gateway","")}/{t.get("kind","")} Rs{t.get("amount","")}')

        print(f'  SHOPIFY: fin={fin} | fulfillment={ful_status} | gw={gw}')
        print(f'  Payment: captured={captured}/{sh.get("total_price","")} | txns: {"; ".join(txn_details)}')

        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        fuls = r_ful.json().get('fulfillments', [])
        for f in fuls:
            print(f'  Fulfillment: id={f.get("id","")} | status={f.get("status","")} | tracking={f.get("tracking_number","")} | company={f.get("tracking_company","")}')

    # Clickpost tracking
    try:
        r_track = requests.get('https://www.clickpost.in/api/v2/track-order/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb, 'cp_id': cp_id},
            timeout=15)
        tr = r_track.json()
        if tr.get('meta', {}).get('success'):
            latest = tr.get('result', {}).get(awb, {}).get('latest_status', {})
            desc = latest.get('clickpost_status_description', '')
            remark = latest.get('remark', '')
            print(f'  TRACKING: {desc} | {remark}')
        else:
            print(f'  TRACKING: API fail')
    except Exception as e:
        print(f'  TRACKING error: {e}')

    time.sleep(0.5)

print(f'\n\nVerification complete.')
