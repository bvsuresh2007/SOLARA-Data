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

orders = ['SOL1204003','SOL1204001','SOL1203988','SOL1203978','SOL1203970','SOL1203961',
          'SOL1203952','SOL1203912','SOL1203900','SOL1203882','SOL1203828','SOL1203782',
          'SOL1203749','SOL1203717','SOL1203681','SOL1203909','SOL1203815','SOL1203773','SOL1203762']

for sol in orders:
    print(f'\n{"="*80}')
    print(f'=== {sol} ===')

    # Get SO
    r = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','in',[0,1]]]),
                'fields': json.dumps(['name','docstatus','customer_name','grand_total','custom_order_type','custom_cod_amount','shipping_address_name','shopify_order_id']),
                'limit_page_length': 1}, timeout=20)
    sos = r.json().get('data', [])

    if not sos:
        print('  NOT ON ATLAS')
        try:
            r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders.json', headers=SHOP_H,
                params={'name': sol, 'status': 'any', 'limit': 1}, timeout=15)
            sh_orders = r_sh.json().get('orders', [])
            if sh_orders:
                o = sh_orders[0]
                sa = o.get('shipping_address') or {}
                print(f'  Shopify: {o.get("financial_status","")} | Rs {o.get("total_price","")} | gateway={o.get("payment_gateway_names","")}')
                nm = sa.get("name","")
                ct = sa.get("city","")
                pr = sa.get("province","")
                zp = sa.get("zip","")
                print(f'  Ship to: {nm} | {ct} {pr} PIN {zp}')
                items = o.get('line_items', [])
                for it in items:
                    sk = it.get("sku","")
                    qt = it.get("quantity",0)
                    print(f'  SKU: {sk} x{qt}')
                pin = zp
                if pin:
                    for ot in ['PREPAID','COD']:
                        try:
                            r_cp = requests.get('https://www.clickpost.in/api/v1/recommendation_api/',
                                params={'key': CP_KEY, 'pickup_pincode': '501218', 'drop_pincode': pin,
                                        'order_type': ot, 'cod_value': '0' if ot=='PREPAID' else str(o.get('total_price','0'))},
                                timeout=10)
                            cp = r_cp.json()
                            pref = cp.get('result', {}).get('preference_array', [])
                            couriers = []
                            for p in pref[:3]:
                                cn = p.get("courier_name","")
                                ci = p.get("cp_id","")
                                couriers.append(f'{cn}(id={ci})')
                            svc = couriers if couriers else ["NOT SERVICEABLE"]
                            print(f'  Svc [{ot}]: {svc}')
                        except Exception as e:
                            print(f'  Svc [{ot}]: CHECK FAILED {e}')
        except Exception as e:
            print(f'  Shopify fetch error: {e}')
        time.sleep(0.5)
        continue

    so = sos[0]
    so_name = so['name']
    oid = so.get('shopify_order_id','')

    # Get SO items
    try:
        r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=20)
        so_full = r_so.json().get('data', {})
        items = so_full.get('items', [])
        skus_parts = []
        has_ghost = False
        for it in items:
            ic = it.get('item_code','')
            qt = int(it.get('qty',0))
            skus_parts.append(f'{ic} x{qt}')
            if not ic.strip():
                has_ghost = True
        print(f'  SO: {so_name} | {so.get("customer_name","")} | Rs {so.get("grand_total","")} | {so.get("custom_order_type","")} | COD={so.get("custom_cod_amount",0)}')
        print(f'  SKUs: {", ".join(skus_parts)}')
        if has_ghost:
            print(f'  *** GHOST SKU DETECTED ***')
    except Exception as e:
        print(f'  SO items fetch error: {e}')
        items = []

    # Get shipping address PIN
    addr_name = so.get('shipping_address_name','')
    pin = ''
    if addr_name:
        try:
            r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H,
                params={'fields': json.dumps(['pincode','city','state','phone'])}, timeout=15)
            ad = r_a.json().get('data', {})
            pin = str(ad.get('pincode',''))
            print(f'  Address: {ad.get("city","")} {ad.get("state","")} PIN {pin} | Phone: {ad.get("phone","")}')
        except:
            print(f'  Address: FETCH FAILED')

    # Shopify payment
    if oid:
        try:
            r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}/transactions.json', headers=SHOP_H, timeout=15)
            txns = r_txn.json().get('transactions', [])
            total_captured = 0
            for t in txns:
                if t.get('kind') in ('capture','sale') and t.get('status') == 'success':
                    total_captured += float(t.get('amount','0'))
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}.json', headers=SHOP_H, timeout=15)
            sh_ord = r_ord.json().get('order', {})
            total_price = float(sh_ord.get('total_price', 0))
            gw_names = sh_ord.get('payment_gateway_names', [])
            fin_status = sh_ord.get("financial_status","")
            print(f'  Payment: {fin_status} | gateways={gw_names} | captured={total_captured}/{total_price}')
        except Exception as e:
            print(f'  Payment: FETCH ERROR {e}')

    # Check DN status
    try:
        r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner','shopify_fulfillment_id']),
                    'limit_page_length': 5}, timeout=20)
        dns = r_dn.json().get('data', [])
        for d in dns:
            ds_label = {0:'Draft',1:'Submitted',2:'Cancelled'}.get(d.get('docstatus',0),'?')
            awb = d.get("awb_number","") or ""
            cp = d.get("courier_partner","") or ""
            print(f'  DN: {d["name"]} | {ds_label} | AWB={awb} | {cp}')
    except:
        dns = []
        print(f'  DN: FETCH FAILED')

    # If submitted DN with no AWB, check error log
    for d in dns:
        if d.get('docstatus') == 1 and not d.get('awb_number'):
            try:
                r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                    params={'filters': json.dumps([['error','like','%'+d["name"]+'%']]),
                            'fields': json.dumps(['error','creation']),
                            'order_by': 'creation desc', 'limit_page_length': 1}, timeout=15)
                errs = r_err.json().get('data', [])
                if errs:
                    err = str(errs[0].get('error',''))
                    found_line = False
                    for line in err.split('\n'):
                        ll = line.lower()
                        keywords = ['clickpost','serviceable','cod','order_type','pincode','error','fail','negative','stock','not service','drop','invalid','preference']
                        if any(k in ll for k in keywords):
                            print(f'  ERR: {line.strip()[:180]}')
                            found_line = True
                            break
                    if not found_line:
                        lines = [l.strip() for l in err.split('\n') if l.strip()]
                        if lines:
                            print(f'  ERR: {lines[-1][:180]}')
                else:
                    print(f'  ERR: No error log found for {d["name"]}')
            except:
                print(f'  ERR: Could not fetch error log')

    # Serviceability check
    if pin:
        order_type = so.get('custom_order_type','Prepaid')
        cod_val = so.get('custom_cod_amount', 0) or 0
        check_types = ['PREPAID'] if order_type == 'Prepaid' else ['COD','PREPAID']
        for ot in check_types:
            try:
                r_cp = requests.get('https://www.clickpost.in/api/v1/recommendation_api/',
                    params={'key': CP_KEY, 'pickup_pincode': '501218', 'drop_pincode': pin,
                            'order_type': ot, 'cod_value': '0' if ot=='PREPAID' else str(cod_val)},
                    timeout=10)
                cp = r_cp.json()
                pref = cp.get('result', {}).get('preference_array', [])
                couriers = []
                for p in pref[:3]:
                    cn = p.get("courier_name","")
                    ci = p.get("cp_id","")
                    couriers.append(f'{cn}(id={ci})')
                svc = couriers if couriers else ["NOT SERVICEABLE"]
                print(f'  Svc [{ot}]: {svc}')
            except:
                print(f'  Svc [{ot}]: CHECK FAILED')

    time.sleep(0.5)

print(f'\n\n{"="*80}')
print('DONE')
