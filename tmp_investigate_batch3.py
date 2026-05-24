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

unique_sols = ['SOL1204715','SOL1204710','SOL1204617','SOL1204551','SOL1204541',
               'SOL1204467','SOL1204435','SOL1204432','SOL1204408','SOL1204568']

for sol in unique_sols:
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
        print(f'  SO: NOT FOUND')
        # Try Shopify search
        r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json',
            headers=SHOP_H, params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
        sh_orders = r_sh.json().get('orders', [])
        if sh_orders:
            o = sh_orders[0]
            sa = o.get('shipping_address', {})
            print(f'  Shopify: #{o.get("order_number","")} | {o.get("financial_status","")} | {o.get("fulfillment_status","")}')
            print(f'  Customer: {sa.get("name","")} | {sa.get("city","")} {sa.get("province","")} PIN {sa.get("zip","")}')
            print(f'  Total: {o.get("total_price","")} | Gateway: {",".join(o.get("payment_gateway_names",[]))}')
            items = o.get('line_items', [])
            for it in items:
                print(f'    SKU={it.get("sku","")} | {it.get("title","")} x{it.get("quantity",0)} @ {it.get("price","")}')
            r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{o["id"]}/transactions.json', headers=SHOP_H, timeout=15)
            txns = r_txn.json().get('transactions', [])
            captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
            print(f'  Payment: captured={captured}/{o.get("total_price","")} | fin={o.get("financial_status","")}')
        else:
            print(f'  Shopify: NOT FOUND either')
        continue

    so = sos[0]
    so_name = so['name']
    shopify_oid = so.get('shopify_order_id', '')
    addr_name = so.get('shipping_address_name', '')
    cust = so.get('customer_name', '')
    otype = so.get('custom_order_type', '') or ''
    cod = float(so.get('custom_cod_amount', 0) or 0)
    total = float(so.get('grand_total', 0) or 0)

    print(f'  SO: {so_name} | ds={so.get("docstatus",0)} | {cust} | {otype} | COD={cod} | Total={total}')
    print(f'  Addr: {addr_name}')

    # SO items with child names
    r_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_full.json().get('data', {})
    items_list = so_full.get('items', [])
    ghost_items = []
    for it in items_list:
        ic = it.get('item_code', '') or ''
        cn = it.get('name', '')
        qty = int(it.get('qty', 0))
        rate = float(it.get('rate', 0) or 0)
        print(f'    item_code="{ic}" | qty={qty} | rate={rate} | child={cn}')
        if not ic or ic.strip() == '':
            ghost_items.append(cn)

    if ghost_items:
        print(f'  *** GHOST SKU: {len(ghost_items)} items with blank item_code ***')

    # Address details
    pin = ''
    if addr_name:
        r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
        ad = r_a.json().get('data', {})
        pin = str(ad.get('pincode', ''))
        print(f'  Address: {ad.get("city","")} {ad.get("state","")} PIN={pin} | Phone={ad.get("phone","")}')

        # Serviceability check
        if pin:
            payload = [{'pickup_pincode': '501218', 'drop_pincode': pin, 'order_type': 'PREPAID',
                        'cod_value': 0, 'delivery_type': 'FORWARD', 'item': 'DGS',
                        'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': 1000}]
            r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
                json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
            svc = r_svc.json()
            if svc.get('meta', {}).get('success'):
                results = svc.get('result', [])
                if results and results[0].get('preference_array'):
                    couriers = [c.get('courier_name','') + '(id=' + str(c.get('courier_id','')) + ')' for c in results[0]['preference_array']]
                    print(f'  Serviceable PREPAID: {", ".join(couriers)}')
                else:
                    print(f'  NOT SERVICEABLE (PREPAID)')

            if cod > 0 or otype in ('PPCOD', 'COD'):
                payload2 = [{'pickup_pincode': '501218', 'drop_pincode': pin, 'order_type': 'COD',
                            'cod_value': cod if cod > 0 else total, 'delivery_type': 'FORWARD', 'item': 'DGS',
                            'weight': 500, 'length': 30, 'breadth': 20, 'height': 15, 'invoice_value': 1000}]
                r_svc2 = requests.post('https://www.clickpost.in/api/v1/recommendation_api/?key=' + CP_KEY + '&username=solara',
                    json=payload2, headers={'Content-Type': 'application/json'}, timeout=10)
                svc2 = r_svc2.json()
                if svc2.get('meta', {}).get('success'):
                    results2 = svc2.get('result', [])
                    if results2 and results2[0].get('preference_array'):
                        couriers2 = [c.get('courier_name','') + '(id=' + str(c.get('courier_id','')) + ')' for c in results2[0]['preference_array']]
                        print(f'  Serviceable COD: {", ".join(couriers2)}')
                    else:
                        print(f'  NOT SERVICEABLE (COD)')

    # DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id']),
                'limit_page_length': 10}, timeout=15)
    dns = r_dn.json().get('data', [])
    for d in dns:
        awb = d.get('awb_number', '') or ''
        cp = d.get('courier_partner', '') or ''
        ful = d.get('shopify_fulfillment_id', '') or ''
        print(f'  DN: {d["name"]} | ds={d.get("docstatus",0)} | AWB={awb} | {cp} | ful={ful}')

    # Error logs for submitted DNs with no AWB
    submitted_no_awb = [d for d in dns if d.get('docstatus') == 1 and not (d.get('awb_number') or '')]
    for d in submitted_no_awb:
        dn_n = d['name']
        try:
            r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                params={'filters': json.dumps([['error','like','%'+dn_n+'%']]),
                        'fields': json.dumps(['error','creation']),
                        'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
            errs = r_err.json().get('data', [])
            if errs:
                err = str(errs[0].get('error',''))
                for line in err.split('\n'):
                    ll = line.lower()
                    if any(k in ll for k in ['clickpost','serviceable','cod','pincode','error','fail','stock','negative','mismatch','address','phone','drop']):
                        print(f'  ERR({dn_n}): {line.strip()[:200]}')
        except:
            pass

    # Shopify payment info
    if shopify_oid:
        try:
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh_ord = r_ord.json().get('order', {})
            fin = sh_ord.get('financial_status', '')
            gw = ','.join(sh_ord.get('payment_gateway_names', []))
            tp = float(sh_ord.get('total_price', 0))
            ful_status = sh_ord.get('fulfillment_status', '') or 'unfulfilled'
            sa = sh_ord.get('shipping_address', {})

            r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
            txns = r_txn.json().get('transactions', [])
            captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
            expected_cod = max(tp - captured, 0)
            expected_type = 'Prepaid' if fin == 'paid' else 'PPCOD' if fin == 'partially_paid' else 'COD'

            print(f'  Shopify: fin={fin} | gw={gw} | total={tp} | captured={captured} | expected_type={expected_type} | expected_cod={expected_cod}')
            print(f'  Shopify addr: {sa.get("name","")} | {sa.get("city","")} {sa.get("province","")} PIN {sa.get("zip","")}')
            print(f'  Shopify fulfillment: {ful_status}')

            # Check Atlas vs Shopify address match
            if addr_name and sa.get('zip'):
                atlas_pin = pin
                shop_pin = str(sa.get('zip', ''))
                if atlas_pin != shop_pin:
                    print(f'  *** PIN MISMATCH: Atlas={atlas_pin} vs Shopify={shop_pin} ***')
        except Exception as e:
            print(f'  Shopify ERR: {e}')

    time.sleep(0.5)
