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
    ('SOL1204765', 'SHPDN27-13634', '68509742162', 'Bluedart'),
    ('SOL1204903', 'SHPDN27-13178', '50938529261', 'Bluedart'),
    ('SOL1204907', 'SHPDN27-13175', '50938529283', 'Bluedart'),
    ('SOL1204975', 'SHPDN27-13553', '29044411211280', 'Delhivery'),
    ('SOL1205129', 'SHPDN27-12989', '50938529305', 'Bluedart'),
]

for sol, dn, awb, courier in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | DN={dn} | AWB={awb} ===')

    # 1. Atlas DN check
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    d = r_dn.json().get('data', {})
    print(f'  ATLAS DN: ds={d.get("docstatus")} | awb={d.get("awb_number","")} | courier={d.get("courier_partner","")}')
    print(f'  Customer: {d.get("customer_name","")} | Total: {d.get("grand_total",0)}')
    items = d.get('items', [])
    skus = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",1))}' for it in items])
    print(f'  Items: {skus}')

    # 2. Atlas SO check
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','custom_order_type','custom_cod_amount','grand_total','shopify_order_id']),
                'limit_page_length': 1}, timeout=15)
    so = r_so.json().get('data', [{}])[0]
    shopify_oid = so.get('shopify_order_id', '')
    print(f'  ATLAS SO: {so.get("name","")} | ds={so.get("docstatus")} | type={so.get("custom_order_type","")} | COD={so.get("custom_cod_amount",0)} | Total={so.get("grand_total",0)}')

    # 3. Shopify order check - payment, fulfillment, tracking
    if shopify_oid:
        r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
        sh = r_ord.json().get('order', {})
        fin = sh.get('financial_status', '')
        gw = ', '.join(sh.get('payment_gateway_names', []))
        total = sh.get('total_price', '')
        ful_status = sh.get('fulfillment_status', '')

        # Transactions
        r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
        txns = r_txn.json().get('transactions', [])
        captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
        txn_details = []
        for t in txns:
            if t.get('status') == 'success':
                txn_details.append(f'{t.get("gateway","")}/{t.get("kind","")} Rs{t.get("amount","")}')

        print(f'  SHOPIFY: fin={fin} | fulfillment={ful_status} | gw={gw}')
        print(f'  Payment: captured={captured}/{total} | txns: {"; ".join(txn_details)}')

        # Fulfillment tracking
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        fuls = r_ful.json().get('fulfillments', [])
        for f in fuls:
            print(f'  Fulfillment: id={f.get("id","")} | status={f.get("status","")} | tracking={f.get("tracking_number","")} | company={f.get("tracking_company","")}')

    # 4. Clickpost label check
    try:
        r_label = requests.post('https://www.clickpost.in/api/v1/shipping-label/',
            params={'username': 'solara', 'key': CP_KEY},
            json={'waybill': awb, 'courier_partner': 5 if courier == 'Bluedart' else 4},
            headers={'Content-Type': 'application/json'}, timeout=15)
        label_resp = r_label.json()
        if label_resp.get('meta', {}).get('success'):
            label_url = label_resp.get('result', '')
            if label_url:
                print(f'  LABEL: Available ✓ ({label_url[:80]}...)')
            else:
                print(f'  LABEL: API success but no URL')
        else:
            print(f'  LABEL: {label_resp.get("meta",{}).get("message","")}')
    except Exception as e:
        print(f'  LABEL check error: {e}')

    # 5. Clickpost tracking status
    try:
        cp_id_track = 5 if courier == 'Bluedart' else 4
        r_track = requests.get('https://www.clickpost.in/api/v2/track-order/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb, 'cp_id': cp_id_track},
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
