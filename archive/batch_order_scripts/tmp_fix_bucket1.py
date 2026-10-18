import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'
r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200: return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(3)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'    Script error: {exc[:300]}')
        return None
    return msg

# Bucket 1: Submitted DN, no AWB — create Clickpost AWB (Delhivery first, Bluedart fallback)
orders = [
    ('SOL1205837', 'SHPDN27-14331'),
    ('SOL1205770', 'SHPDN27-14375'),
    ('SOL1205758', 'SHPDN27-14386'),
    ('SOL1205755', 'SHPDN27-14389'),
    ('SOL1205723', 'SHPDN27-14412'),
    ('SOL1205712', 'SHPDN27-14420'),
    ('SOL1205689', 'SHPDN27-14435'),
    ('SOL1205678', 'SHPDN27-14442'),
    ('SOL1205668', 'SHPDN27-14450'),
    ('SOL1205654', 'SHPDN27-14460'),
    ('SOL1205640', 'SHPDN27-14470'),
    ('SOL1205635', 'SHPDN27-14474'),
    ('SOL1205596', 'SHPDN27-14506'),
    ('SOL1205573', 'SHPDN27-14523'),
    ('SOL1205572', 'SHPDN27-14524'),
    ('SOL1205541', 'SHPDN27-14549'),
    ('SOL1205510', 'SHPDN27-14568'),
]

results = []

for sol, dn in orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} | {dn} ===')

    # Get DN details
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    d = r_dn.json().get('data', {})
    shopify_oid = d.get('shopify_order_id', '')
    addr_name = d.get('shipping_address_name', '')
    otype = d.get('custom_order_type', '') or 'Prepaid'
    cod_amount = float(d.get('custom_cod_amount', 0) or 0)
    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    items_list = d.get('items', [])

    # Get address
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr = r_a.json().get('data', {})
    pin = str(addr.get('pincode', ''))
    drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
    phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10: phone = phone[-10:]
    city = addr.get('city', '')
    state = addr.get('state', '')
    email = addr.get('email_id', '') or 'noreply@solara.in'
    cust_name = addr.get('address_title', '')

    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0: total_weight = len(items_list) * 0.5
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200: total_weight_g = 500

    items_str = ', '.join([it.get('item_code','') + ' x' + str(int(it.get('qty',1))) for it in items_list])
    print(f'  {cust_name} | {city} {state} PIN={pin} | {otype} COD={cod_amount}')
    print(f'  Items: {items_str} | Weight: {total_weight_g}g | Total: {grand_total}')

    # Check serviceability
    cp_otype = 'COD' if otype == 'PPCOD' else 'PREPAID'
    r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/',
        params={'key': CP_KEY},
        json=[{'reference_number': '1', 'pickup_pincode': '501218', 'drop_pincode': pin,
               'order_type': cp_otype, 'delivery_type': 'FORWARD', 'invoice_value': grand_total,
               'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g, 'item': 'DGS',
               'cod_value': cod_amount if cp_otype == 'COD' else 0}],
        timeout=15)
    svc_data = r_svc.json()
    pref = []
    if svc_data.get('meta', {}).get('success'):
        res_list = svc_data.get('result', [])
        if res_list: pref = res_list[0].get('preference_array', [])
    courier_ids = [p.get('cp_id', 0) for p in pref]
    courier_names = [p.get('courier_name', '') for p in pref]
    print(f'  Serviceable: {courier_names}')

    if not courier_ids:
        print(f'  NOT SERVICEABLE')
        results.append((sol, dn, 'NOT_SERVICEABLE', '', '', pin))
        continue

    # Try Delhivery (4) first, then Bluedart (5)
    cp_try = [cp for cp in [4, 5] if cp in courier_ids]
    if not cp_try: cp_try = courier_ids
    cp_names_map = {4: 'Delhivery', 5: 'Bluedart'}

    order_type = 'PREPAID'
    cod_value = 0
    if otype in ('PPCOD', 'COD'):
        order_type = 'COD'
        cod_value = cod_amount

    new_awb = ''
    courier = ''
    for cp_id in cp_try:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-12T10:00:00Z',
            },
            'drop_info': {
                'drop_name': cust_name, 'drop_phone': phone,
                'drop_address': drop_address, 'drop_city': city,
                'drop_state': state, 'drop_pincode': pin,
                'drop_country': 'IN', 'drop_email': email,
            },
            'shipment_details': {
                'order_type': order_type, 'invoice_value': grand_total, 'reference_number': sol,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_value, 'courier_partner': cp_id,
                'invoice_number': dn, 'invoice_date': d.get('posting_date', ''),
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(d.get('net_total', 0) or 0),
                'is_seller_registered_under_gst': True, 'place_of_supply': state,
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0,
                'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
                'invoice_number': dn, 'invoice_date': d.get('posting_date', ''),
            },
            'additional': {
                'label': True,
                'return_info': {
                    'name': 'WIN THE BUY BOX PVT LTD', 'phone': '9573652101',
                    'address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                    'city': 'Hyderabad', 'state': 'Telangana', 'pincode': '501218', 'country': 'IN',
                },
                'async': False,
            },
        }
        cname = cp_names_map.get(cp_id, str(cp_id))
        print(f'  Trying {cname}...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})
        if meta.get('success') and meta.get('status') == 200:
            new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cname
            print(f'  AWB={new_awb} via {courier}')
            break
        else:
            err = meta.get('message', '')
            print(f'  FAIL {cname}: {err[:150]}')
            # If cached, try with -R1 suffix
            if 'already placed' in err.lower():
                cp_payload['shipment_details']['reference_number'] = sol + '-R1'
                print(f'  Retrying with -R1...')
                r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                cp_resp2 = r_cp2.json()
                meta2 = cp_resp2.get('meta', {})
                if meta2.get('success') and meta2.get('status') == 200:
                    new_awb = str(cp_resp2.get('result', {}).get('waybill', ''))
                    courier = cname
                    print(f'  AWB={new_awb} via {courier} (R1)')
                    break
                else:
                    print(f'  FAIL {cname} R1: {meta2.get("message","")[:150]}')

    if not new_awb:
        print(f'  ALL COURIERS FAILED')
        results.append((sol, dn, 'COURIER_FAIL', '', '', pin))
        continue

    # Save AWB to DN
    sn = 'tmp_nawb_' + dn.replace('-','_').lower()
    script = "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + new_awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + dn + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
    msg = run_server_script(sn, script)
    print(f'  DN AWB saved: {msg}')

    # Shopify fulfillment
    if shopify_oid:
        tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
        r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
        fos = r_fo.json().get('fulfillment_orders', [])
        open_fos = []
        for fo in fos:
            if fo.get('status') in ('open', 'in_progress'):
                fo_items = [{'id': li['id'], 'quantity': li.get('fulfillable_quantity', 0)}
                           for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
                if fo_items:
                    open_fos.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_items})
        if open_fos:
            payload = {'fulfillment': {'line_items_by_fulfillment_order': open_fos,
                'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
            r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
            if r_f.status_code in (200, 201):
                print(f'  Shopify fulfillment created')
            else:
                print(f'  Shopify FAIL: {r_f.status_code} {r_f.text[:150]}')
        else:
            # Try update_tracking on existing
            r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
            existing = r_ful.json().get('fulfillments', [])
            if existing:
                ful_id = str(existing[-1].get('id', ''))
                payload = {'fulfillment': {'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
                r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                print(f'  Shopify tracking updated: {r_u.status_code}')
            else:
                print(f'  No Shopify fulfillment options')

    results.append((sol, dn, 'OK', new_awb, courier, pin))
    time.sleep(0.5)

print(f'\n\n{"="*80}')
print(f'BUCKET 1 SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[2] == 'OK']
ns = [r for r in results if r[2] == 'NOT_SERVICEABLE']
fail = [r for r in results if r[2] == 'COURIER_FAIL']
for r in ok:
    print(f'  OK   {r[0]} | {r[1]} | AWB={r[3]} | {r[4]} | PIN={r[5]}')
for r in fail:
    print(f'  FAIL {r[0]} | {r[1]} | PIN={r[5]} | All couriers rejected')
for r in ns:
    print(f'  N/S  {r[0]} | {r[1]} | PIN={r[5]} | Not serviceable')
print(f'\n  Total: {len(ok)} OK | {len(fail)} courier fail | {len(ns)} not serviceable')
