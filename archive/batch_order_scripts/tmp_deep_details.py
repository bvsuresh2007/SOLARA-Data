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

orders = [
    ('REP-2627-SHP-00202', 'Gopi .'),
    ('SOL1201901', 'Suhas Kulkarni'),
    ('SOL1196443', 'Bhawna Panjwani'),
    ('REP-2627-SHP-00271', 'Mohammed Arshad'),
    ('SOL1198284', 'Teresa Moktan'),
    ('SOL1201623', 'Monica Chahal'),
]

for sol, cust in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} | {cust} ===')

    # Get SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['name' if sol.startswith('REP') else 'shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','grand_total','custom_order_type',
                                      'custom_cod_amount','shopify_order_id','shipping_address_name']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])
    if not sos and sol.startswith('REP'):
        r_so2 = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['name','like',sol+'%']]),
                    'fields': json.dumps(['name','docstatus','customer_name','grand_total','custom_order_type',
                                          'custom_cod_amount','shopify_order_id','shipping_address_name']),
                    'limit_page_length': 5}, timeout=15)
        sos = r_so2.json().get('data', [])

    for so in sos:
        so_name = so['name']
        otype = so.get('custom_order_type', '') or ''
        cod = float(so.get('custom_cod_amount', 0) or 0)
        total = float(so.get('grand_total', 0) or 0)
        shopify_oid = so.get('shopify_order_id', '') or ''
        addr = so.get('shipping_address_name', '') or ''

        print(f'  SO: {so_name} | ds={so.get("docstatus",0)} | {otype} | COD={cod} | Total={total}')

        # SO items
        r_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
        so_full = r_full.json().get('data', {})
        items_list = so_full.get('items', [])
        for it in items_list:
            ic = it.get('item_code', '') or ''
            qty = int(it.get('qty', 0))
            rate = float(it.get('rate', 0) or 0)
            print(f'    SKU: {ic} x{qty} @ {rate}')

        # Address
        if addr:
            r_a = requests.get(f'{BASE}/api/resource/Address/{addr}', headers=H, timeout=15)
            ad = r_a.json().get('data', {})
            print(f'  Address: {ad.get("city","")} {ad.get("state","")} PIN={ad.get("pincode","")} | Phone={ad.get("phone","")}')

        # Shopify payment (only for SOL orders)
        if shopify_oid:
            try:
                r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
                sh_ord = r_ord.json().get('order', {})
                fin = sh_ord.get('financial_status', '')
                gw = ','.join(sh_ord.get('payment_gateway_names', []))
                tp = float(sh_ord.get('total_price', 0))
                ful_status = sh_ord.get('fulfillment_status', '') or 'unfulfilled'

                r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
                txns = r_txn.json().get('transactions', [])
                captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')

                print(f'  Shopify: fin={fin} | gw={gw} | total={tp} | captured={captured} | fulfillment={ful_status}')
            except Exception as e:
                print(f'  Shopify ERR: {e}')
        else:
            print(f'  Shopify: no order_id (replacement order)')

    # All DNs by customer name
    r_dns = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['customer_name','=',cust]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_order_number','creation','is_replacement']),
                'order_by': 'creation desc',
                'limit_page_length': 15}, timeout=15)
    dns = r_dns.json().get('data', [])

    if dns:
        print(f'  --- All DNs for {cust} ---')
        for d in dns:
            awb = d.get('awb_number', '') or ''
            cp = d.get('courier_partner', '') or ''
            ds = d.get('docstatus', 0)
            ds_label = {0: 'Draft', 1: 'Submitted', 2: 'Cancelled'}
            son = d.get('shopify_order_number', '') or ''
            is_rep = d.get('is_replacement', 0)
            creation = str(d.get('creation', ''))[:10]
            print(f'    {d["name"]} | {ds_label.get(ds,ds)} | AWB={awb} | {cp} | SON={son} | rep={is_rep} | {creation}')

    time.sleep(0.3)
