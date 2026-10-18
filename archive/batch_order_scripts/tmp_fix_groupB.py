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

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'    Script create FAIL: {r.status_code} {r.text[:200]}')
        return None
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

# Group B: Submitted DN, no AWB — Delhivery rejected PIN
# Fix: check Bluedart serviceability, create Clickpost order with Bluedart (cp_id=5),
# if Bluedart fails try Delhivery (cp_id=4), save AWB to DN, sync Shopify
orders = [
    ('SOL1200450', 'SHPDN27-12343', 'PPCOD'),
    ('SOL1201217', 'SHPDN27-12384', 'PPCOD'),
    ('SOL1204033', 'SHPDN27-12947', 'PPCOD'),
    ('SOL1202791', 'SHPDN27-12831', 'PPCOD'),
    ('SOL1201544', 'SHPDN27-12457', 'Prepaid'),
    ('SOL1201706', 'SHPDN27-12479', 'Prepaid'),
    ('SOL1201965', 'SHPDN27-12509', 'Prepaid'),
    ('SOL1201991', 'SHPDN27-12511', 'Prepaid'),
    ('SOL1202163', 'SHPDN27-12529', 'Prepaid'),
    ('SOL1202432', 'SHPDN27-12556', 'Prepaid'),
    ('SOL1202463', 'SHPDN27-12558', 'Prepaid'),
    ('SOL1203884', 'SHPDN27-12718', 'Prepaid'),
    ('SOL1202033', 'SHPDN27-13718', 'Prepaid'),
    ('SOL1203044', 'SHPDN27-13790', 'Prepaid'),
]

# Step 1: Check serviceability for all PINs
print('='*80)
print('STEP 1: Checking serviceability for all Group B PINs')
print('='*80)

svc_results = {}
for sol, dn, otype in orders:
    # Get DN details
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
    d = r_dn.json().get('data', {})
    addr_name = d.get('shipping_address_name', '')

    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr = r_a.json().get('data', {})
    pin = str(addr.get('pincode', ''))

    # Get SO for COD amount
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['custom_shopify_order_number','=',sol]]),
                'fields': json.dumps(['custom_cod_amount','custom_order_type']),
                'limit_page_length': 1}, timeout=15)
    so_data = r_so.json().get('data', [{}])[0]
    cod_amount = float(so_data.get('custom_cod_amount', 0) or 0)

    cp_otype = 'COD' if otype == 'PPCOD' else 'PREPAID'

    r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/',
        params={'key': CP_KEY},
        json=[{'reference_number': '1', 'pickup_pincode': '501218', 'drop_pincode': pin,
               'order_type': cp_otype, 'delivery_type': 'FORWARD', 'invoice_value': float(d.get('grand_total', 1000)),
               'length': 30, 'breadth': 20, 'height': 15, 'weight': 500, 'item': 'DGS',
               'cod_value': cod_amount if cp_otype == 'COD' else 0}],
        timeout=15)
    svc_data = r_svc.json()
    pref = []
    if svc_data.get('meta', {}).get('success'):
        res_list = svc_data.get('result', [])
        if res_list and isinstance(res_list, list):
            pref = res_list[0].get('preference_array', [])

    courier_ids = [p.get('cp_id', 0) for p in pref]
    courier_names = [p.get('courier_name', '') for p in pref]

    svc_results[sol] = {
        'pin': pin, 'couriers': courier_ids, 'courier_names': courier_names,
        'dn': dn, 'otype': otype, 'cp_otype': cp_otype, 'cod': cod_amount,
        'addr': addr, 'dn_data': d
    }

    svc_str = 'SERVICEABLE' if courier_ids else 'NOT SERVICEABLE'
    print(f'  {sol} PIN={pin} {cp_otype}: {svc_str} -> {courier_names}')

# Separate serviceable vs not
serviceable = {k: v for k, v in svc_results.items() if v['couriers']}
not_serviceable = {k: v for k, v in svc_results.items() if not v['couriers']}

print(f'\n  Serviceable: {len(serviceable)} | Not serviceable: {len(not_serviceable)}')
if not_serviceable:
    print(f'  NOT SERVICEABLE: {list(not_serviceable.keys())}')

# Step 2: Create Clickpost AWBs for serviceable orders
print(f'\n{"="*80}')
print(f'STEP 2: Creating Clickpost AWBs for {len(serviceable)} serviceable orders')
print(f'{"="*80}')

results = []

for sol, info in serviceable.items():
    dn = info['dn']
    d = info['dn_data']
    addr = info['addr']
    pin = info['pin']
    couriers = info['couriers']
    otype = info['otype']
    cp_otype = info['cp_otype']
    cod_amount = info['cod']

    shopify_oid = d.get('shopify_order_id', '') or ''

    drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
    phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10: phone = phone[-10:]

    items_list = d.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0: total_weight = len(items_list) * 0.5
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200: total_weight_g = 500
    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)

    # Count cancelled DNs for ref suffix
    r_cdn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['custom_shopify_order_number','=',sol],['docstatus','=',2]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 0}, timeout=10)
    cancelled_count = len(r_cdn.json().get('data', []))
    ref = sol if cancelled_count == 0 else f'{sol}-R{cancelled_count}'

    order_type = 'PREPAID'
    cod_value = 0
    if cp_otype == 'COD':
        order_type = 'COD'
        cod_value = cod_amount

    print(f'\n  --- {sol} | DN={dn} | PIN={pin} | {order_type} COD={cod_value} ---')
    print(f'  Customer: {d.get("customer_name","")} | Phone={phone} | Weight={total_weight_g}g')

    item_strs = [str(it.get("item_code","")) + " x" + str(int(it.get("qty",1))) for it in items_list]
    print(f'  Items: {", ".join(item_strs)}')
    print(f'  Ref: {ref} | Couriers available: {info["courier_names"]}')

    # Try preferred courier first (Bluedart=5 preferred over Delhivery=4)
    cp_try_order = sorted(couriers, key=lambda x: 0 if x == 5 else 1)
    cp_names = {4: 'Delhivery', 5: 'Bluedart'}

    new_awb = None
    used_courier = None
    used_cp_id = None

    for cp_id in cp_try_order:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-12T10:00:00Z',
            },
            'drop_info': {
                'drop_name': d.get('customer_name', ''), 'drop_phone': phone,
                'drop_address': drop_address, 'drop_city': addr.get('city', ''),
                'drop_state': addr.get('state', ''), 'drop_pincode': pin,
                'drop_country': 'IN', 'drop_email': addr.get('email_id', '') or 'noreply@solara.in',
            },
            'shipment_details': {
                'order_type': order_type, 'invoice_value': grand_total, 'reference_number': ref,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_value, 'courier_partner': cp_id,
                'invoice_number': dn, 'invoice_date': d.get('posting_date', ''),
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(d.get('net_total', 0) or 0),
                'ewaybill_serial_number': '', 'is_seller_registered_under_gst': True,
                'place_of_supply': addr.get('state', ''), 'cstin': '',
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0,
                'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
                'invoice_number': dn, 'invoice_date': d.get('posting_date', ''), 'hsn_code': '',
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

        print(f'  Trying {cp_names.get(cp_id, cp_id)} (cp_id={cp_id})...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})

        if meta.get('success') and meta.get('status') == 200:
            new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
            used_courier = cp_names.get(cp_id, str(cp_id))
            used_cp_id = cp_id
            print(f'  OK AWB={new_awb} via {used_courier}')
            break
        else:
            err = meta.get('message', '')
            print(f'  FAIL {cp_names.get(cp_id, cp_id)}: {err[:150]}')

    if not new_awb:
        print(f'  ALL COURIERS FAILED for {sol}')
        results.append((sol, 'FAIL', dn, '', '', 'All couriers failed'))
        continue

    # Save AWB to DN
    sn = 'tmp_nawb_' + dn.replace('-','_').lower()
    script = (
        "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + new_awb + "',update_modified=False)\n"
        "frappe.db.set_value('Delivery Note','" + dn + "','courier_partner','" + used_courier + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    if msg:
        print(f'  AWB saved to DN')

    # Sync Shopify tracking
    if shopify_oid:
        tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        existing = r_ful.json().get('fulfillments', [])

        if existing:
            ful_id = str(existing[-1].get('id', ''))
            payload = {'fulfillment': {
                'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': used_courier},
                'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                headers=SHOP_H, json=payload, timeout=15)
            if r_u.status_code in (200, 201):
                print(f'  Shopify tracking updated')
            else:
                print(f'  Shopify tracking FAIL: {r_u.status_code} {r_u.text[:150]}')
        else:
            # Create fulfillment
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
                    'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': used_courier},
                    'notify_customer': True}}
                r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
                if r_f.status_code in (200, 201):
                    print(f'  Shopify fulfillment created')
                else:
                    print(f'  Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:150]}')
            else:
                print(f'  No open FOs on Shopify')
    else:
        print(f'  No shopify_order_id on DN')

    results.append((sol, 'OK', dn, new_awb, used_courier, otype))
    time.sleep(1)

# Summary
print(f'\n\n{"="*80}')
print(f'GROUP B FIX SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] != 'OK']
for r in ok:
    print(f'  OK  {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]} | {r[5]}')
for r in fail:
    print(f'  FAIL {r[0]}: DN={r[2]} | {r[5]}')

if not_serviceable:
    print(f'\n  NOT SERVICEABLE ({len(not_serviceable)} orders — needs CS follow-up):')
    for sol, info in not_serviceable.items():
        print(f'    {sol} PIN={info["pin"]}')

print(f'\n  Total: {len(ok)} OK | {len(fail)} FAIL | {len(not_serviceable)} not serviceable')
