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

# Only investigate orders that need action (not the 6 already shipped)
investigate = [
    # Submitted DN no AWB
    'SOL1204744','SOL1204765','SOL1204903','SOL1204907','SOL1204975','SOL1205032','SOL1205129',
    # Draft DN only
    'SOL1204747','SOL1204751','SOL1204873','SOL1204894','SOL1204918',
    'SOL1205004','SOL1205008','SOL1205037','SOL1205054','SOL1205090',
    # No DN
    'SOL1204795','SOL1204921','SOL1204933',
    # Not on Atlas
    'SOL1204809','SOL1204919','SOL1205015','SOL1205022','SOL1205080',
]

for sol in investigate:
    print(f'\n{"="*80}')
    print(f'=== {sol} ===')

    # Atlas SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','custom_order_type','custom_cod_amount',
                                      'grand_total','shopify_order_id','shipping_address_name']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])

    if not sos:
        # Search Shopify
        r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
            headers=SHOP_H, params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
        sh_orders = r_sh.json().get('orders', [])
        if sh_orders:
            o = sh_orders[0]
            sa = o.get('shipping_address', {})
            fin = o.get('financial_status', '')
            gw = ','.join(o.get('payment_gateway_names', []))
            items = o.get('line_items', [])
            skus = ', '.join([f'{it.get("sku","")} x{it.get("quantity",0)}' for it in items])
            print(f'  NOT ON ATLAS | Shopify: {fin} | {gw} | Total={o.get("total_price","")}')
            print(f'  Customer: {sa.get("name","")} | {sa.get("city","")} {sa.get("province","")} PIN {sa.get("zip","")}')
            print(f'  SKUs: {skus}')
        else:
            print(f'  NOT FOUND anywhere')
        time.sleep(0.3)
        continue

    so = sos[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    addr_name = so.get('shipping_address_name', '')
    otype = so.get('custom_order_type', '') or ''
    cod = float(so.get('custom_cod_amount', 0) or 0)
    total = float(so.get('grand_total', 0) or 0)

    # SO items - check for ghost
    r_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_full.json().get('data', {})
    items_list = so_full.get('items', [])
    ghost = False
    items_str = []
    for it in items_list:
        ic = it.get('item_code', '') or ''
        if not ic:
            ghost = True
            items_str.append(f'GHOST(child={it.get("name","")}) x{int(it.get("qty",0))}')
        else:
            items_str.append(f'{ic} x{int(it.get("qty",0))}')

    print(f'  SO: {so_name} | {so.get("customer_name","")} | {otype} | COD={cod} | Total={total}')
    print(f'  Items: {", ".join(items_str)}')
    if ghost:
        print(f'  *** GHOST SKU ***')

    # Address + serviceability
    pin = ''
    if addr_name:
        r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
        ad = r_a.json().get('data', {})
        pin = str(ad.get('pincode', ''))
        phone = str(ad.get('phone', ''))
        print(f'  Addr: {ad.get("city","")} {ad.get("state","")} PIN={pin} | Phone={phone}')

        if pin:
            ot = 'PREPAID' if otype != 'PPCOD' and otype != 'COD' else 'COD'
            cv = cod if ot == 'COD' else 0
            payload = [{'pickup_pincode': '501218', 'drop_pincode': pin, 'order_type': ot,
                        'cod_value': cv, 'delivery_type': 'FORWARD', 'item': 'DGS',
                        'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': max(total,1)}]
            r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
                json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            svc = r_svc.json()
            if svc.get('meta', {}).get('success'):
                results = svc.get('result', [])
                if results and results[0].get('preference_array'):
                    couriers = [c.get('courier_name','') for c in results[0]['preference_array']]
                    print(f'  Serviceable ({ot}): {", ".join(couriers)}')
                else:
                    print(f'  NOT SERVICEABLE ({ot})')
                    # Try other type
                    alt = 'COD' if ot == 'PREPAID' else 'PREPAID'
                    payload2 = [{'pickup_pincode': '501218', 'drop_pincode': pin, 'order_type': alt,
                                'cod_value': 0 if alt == 'PREPAID' else total, 'delivery_type': 'FORWARD', 'item': 'DGS',
                                'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': max(total,1)}]
                    r_svc2 = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
                        json=payload2, headers={'Content-Type': 'application/json'}, timeout=10)
                    svc2 = r_svc2.json()
                    if svc2.get('meta', {}).get('success') and svc2.get('result', [{}])[0].get('preference_array'):
                        couriers2 = [c.get('courier_name','') for c in svc2['result'][0]['preference_array']]
                        print(f'  Serviceable ({alt}): {", ".join(couriers2)}')

    # Shopify address check
    if shopify_oid:
        try:
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh_ord = r_ord.json().get('order', {})
            fin = sh_ord.get('financial_status', '')
            gw = ','.join(sh_ord.get('payment_gateway_names', []))
            sa = sh_ord.get('shipping_address', {})
            shop_pin = str(sa.get('zip', ''))

            r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
            txns = r_txn.json().get('transactions', [])
            captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')

            print(f'  Shopify: fin={fin} | gw={gw} | captured={captured}/{sh_ord.get("total_price","")}')

            if pin and shop_pin and pin != shop_pin:
                print(f'  *** PIN MISMATCH: Atlas={pin} vs Shopify={shop_pin} ***')
        except:
            pass

    # Error logs for submitted DNs with no AWB
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',1]]),
                'fields': json.dumps(['name','awb_number']),
                'limit_page_length': 5}, timeout=15)
    submitted_dns = r_dn.json().get('data', [])
    for d in submitted_dns:
        if not (d.get('awb_number') or ''):
            dn_n = d['name']
            try:
                r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                    params={'filters': json.dumps([['error','like','%'+dn_n+'%']]),
                            'fields': json.dumps(['error']),
                            'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
                errs = r_err.json().get('data', [])
                if errs:
                    err = str(errs[0].get('error',''))
                    for line in err.split('\n'):
                        ll = line.lower()
                        if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative','mismatch','address','phone','drop','not serv']):
                            print(f'  ERR({dn_n}): {line.strip()[:180]}')
                            break
            except:
                pass

    time.sleep(0.3)
