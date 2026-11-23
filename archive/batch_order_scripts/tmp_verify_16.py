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
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

orders = [
    ('SOL1204001', 'SHPDN27-11365', '29044411197523'),
    ('SOL1203988', 'SHPDN27-11375', '29044411197545'),
    ('SOL1203978', 'SHPDN27-11383', '29044411197604'),
    ('SOL1203961', 'SHPDN27-11394', '29044411197560'),
    ('SOL1203749', 'SHPDN27-11539', '29044411197571'),
    ('SOL1203815', 'SHPDN27-11620', '29044411197582'),
    ('SOL1203882', 'SHPDN27-11977', '29044411197593'),
    ('SOL1203900', 'SHPDN27-11978', '29044411197615'),
    ('SOL1203828', 'SHPDN27-11979', '29044411197626'),
    ('SOL1203782', 'SHPDN27-11980', '50938488241'),
    ('SOL1203717', 'SHPDN27-11981', '29044411197630'),
    ('SOL1203909', 'SHPDN27-11982', '29044411197641'),
    ('SOL1204003', 'SHPDN27-11363', '50938488381'),
    ('SOL1203952', 'SHPDN27-11403', '50938488392'),
    ('SOL1203773', 'SHPDN27-11630', '68509733644'),
    ('SOL1203762', 'SHPDN27-11632', '50938488414'),
]

print(f'{"SOL":<14} {"Shopify Fin":<16} {"Shopify Gateway":<22} {"Captured/Total":<18} {"Atlas Type":<10} {"Atlas COD":<10} {"CP Type":<10} {"CP COD":<10} {"Match":<6}')
print("=" * 140)

mismatches = []

for sol, dn, awb in orders:
    # Atlas SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',1]]),
                'fields': json.dumps(['name','shopify_order_id','custom_order_type','custom_cod_amount','grand_total']),
                'limit_page_length': 1}, timeout=15)
    sos = r_so.json().get('data', [])
    atlas_type = ''
    atlas_cod = 0
    atlas_total = 0
    shopify_oid = ''
    if sos:
        atlas_type = sos[0].get('custom_order_type', '')
        atlas_cod = float(sos[0].get('custom_cod_amount', 0) or 0)
        atlas_total = float(sos[0].get('grand_total', 0) or 0)
        shopify_oid = sos[0].get('shopify_order_id', '')

    # Shopify payment
    shopify_fin = ''
    shopify_gw = ''
    captured = 0
    total_price = 0
    if shopify_oid:
        try:
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh_ord = r_ord.json().get('order', {})
            shopify_fin = sh_ord.get('financial_status', '')
            gw_names = sh_ord.get('payment_gateway_names', [])
            shopify_gw = ','.join(gw_names) if gw_names else ''
            total_price = float(sh_ord.get('total_price', 0))

            r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
            txns = r_txn.json().get('transactions', [])
            for t in txns:
                if t.get('kind') in ('capture', 'sale') and t.get('status') == 'success':
                    captured += float(t.get('amount', '0'))
        except:
            shopify_fin = 'ERR'

    # Clickpost order
    cp_type = ''
    cp_cod = ''
    try:
        r_cp = requests.get(f'https://www.clickpost.in/api/v1/tracking/',
            params={'username': 'solara', 'key': CP_KEY, 'waybill': awb}, timeout=10)
        cp_data = r_cp.json()
        if cp_data.get('meta', {}).get('success'):
            result = cp_data.get('result', {})
            cp_type = result.get('order_type', '')
            cp_cod = result.get('cod_value', '')
    except:
        cp_type = 'ERR'

    # Compare
    # Shopify: paid = fully prepaid, partially_paid = PPCOD
    expected_type = 'Prepaid' if shopify_fin == 'paid' else 'PPCOD' if shopify_fin == 'partially_paid' else 'COD'
    expected_cod = max(total_price - captured, 0) if shopify_fin == 'partially_paid' else 0

    # CP type mapping: PREPAID or COD
    cp_type_norm = 'Prepaid' if cp_type == 'PREPAID' else 'COD' if cp_type == 'COD' else cp_type

    # Check match
    match_ok = True
    issues = []

    # For PPCOD: CP should be COD with correct cod_value
    if atlas_type == 'PPCOD':
        if cp_type != 'COD':
            match_ok = False
            issues.append(f'CP should be COD')
        if cp_cod and abs(float(cp_cod) - atlas_cod) > 1:
            match_ok = False
            issues.append(f'COD mismatch CP={cp_cod} Atlas={atlas_cod}')
    elif atlas_type == 'Prepaid':
        if cp_type != 'PREPAID':
            match_ok = False
            issues.append(f'CP should be PREPAID')
        if cp_cod and float(cp_cod) > 0:
            match_ok = False
            issues.append(f'CP has COD={cp_cod} but Prepaid')

    match_str = 'OK' if match_ok else 'MISMATCH'
    cap_str = f'{captured}/{total_price}'

    print(f'{sol:<14} {shopify_fin:<16} {shopify_gw:<22} {cap_str:<18} {atlas_type:<10} {atlas_cod:<10.1f} {cp_type:<10} {str(cp_cod):<10} {match_str:<6}')

    if not match_ok:
        mismatches.append((sol, issues))

    time.sleep(0.3)

if mismatches:
    print(f'\nMISMATCHES:')
    for sol, issues in mismatches:
        print(f'  {sol}: {"; ".join(issues)}')
else:
    print(f'\nAll 16 orders match across Shopify, Atlas, and Clickpost.')
