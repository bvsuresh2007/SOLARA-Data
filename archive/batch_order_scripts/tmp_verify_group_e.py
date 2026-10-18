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
    ('SOL1204809', 'SHP27-11605', 'SHPDN27-13893', '68509742383', 5),
    ('SOL1204919', 'SHP27-11606', 'SHPDN27-13894', '29044411211560', 4),
    ('SOL1205015', 'SHP27-11607', 'SHPDN27-13895', '29044411211571', 4),
    ('SOL1205022', 'SHP27-11608', 'SHPDN27-13896', '29044411211582', 4),
    ('SOL1205080', 'SHP27-11609', 'SHPDN27-13897', '29044411211593', 4),
]

for sol, so_name, dn_name, awb, cp_id in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} ===')

    # Atlas SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so = r_so.json().get('data', {})
    print(f'  ATLAS SO: {so_name} | ds={so.get("docstatus")} | type={so.get("custom_order_type","")} | COD={so.get("custom_cod_amount",0)} | Total={so.get("grand_total",0)}')
    items = so.get('items', [])
    skus = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",1))}' for it in items])
    print(f'  Items: {skus}')
    print(f'  Ship addr: {so.get("shipping_address_name","")}')

    # Atlas DN
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    d = r_dn.json().get('data', {})
    print(f'  ATLAS DN: {dn_name} | ds={d.get("docstatus")} | awb={d.get("awb_number","")} | courier={d.get("courier_partner","")}')
    print(f'  Customer: {d.get("customer_name","")} | Total: {d.get("grand_total",0)}')

    # Shopify
    shopify_oid = so.get('shopify_order_id', '')
    if shopify_oid:
        r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh = r_ord.json().get('order', {})
        fin = sh.get('financial_status', '')
        gw = ', '.join(sh.get('payment_gateway_names', []))
        ful_status = sh.get('fulfillment_status', '')
        sh_total = sh.get('total_price', '')

        r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
        txns = r_txn.json().get('transactions', [])
        captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
        txn_details = []
        for t in txns:
            if t.get('status') == 'success':
                txn_details.append(f'{t.get("gateway","")}/{t.get("kind","")} Rs{t.get("amount","")}')

        print(f'  SHOPIFY: fin={fin} | fulfillment={ful_status} | gw={gw}')
        print(f'  Payment: captured={captured}/{sh_total} | txns: {"; ".join(txn_details)}')

        # Fulfillments
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
