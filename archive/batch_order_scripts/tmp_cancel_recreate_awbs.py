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

# Orders with stuck AWBs - cancel old, create new
orders = [
    ('REP-2627-SHP-00202', 'Gopi .', 'SHPDN27-06822', '29044411144345'),
    ('SOL1201901', 'Suhas Kulkarni', 'SHPDN27-09462', '29044411170901'),
    ('SOL1196443', 'Bhawna Panjwani', 'SHPDN27-09309', '29044411169442'),
    ('REP-2627-SHP-00271', 'Mohammed Arshad', 'SHPDN27-06824', '29044411144360'),
    ('SOL1198284', 'Teresa Moktan', 'SHPDN27-04960', '29044411127825'),
    ('SOL1201623', 'Monica Chahal', 'SHPDN27-08289', '29044411158636'),
]

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
        print(f'    Script error: {exc[:200]}')
        return None
    return msg

results = []

for sol, cust, dn, old_awb in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} | {cust} | DN={dn} | Old AWB={old_awb} ===')

    # Step 1: Cancel already done in previous run, skip
    print(f'  Step 1: Old AWB {old_awb} already cancelled')


    # Step 2: Get DN details for new Clickpost order
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
    d = r_dn.json().get('data', {})

    addr_name = d.get('shipping_address_name', '')
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr_data = r_a.json().get('data', {})

    drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip()
    items_list = d.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0:
        total_weight = len(items_list) * 0.5
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200:
        total_weight_g = 500

    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    phone = str(addr_data.get('phone', ''))
    if phone:
        phone = phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(phone) > 10:
            phone = phone[-10:]

    pin = str(addr_data.get('pincode', ''))

    # Determine order type from SO
    shopify_oid = d.get('shopify_order_id', '') or ''
    order_type = 'PREPAID'
    cod_value = 0

    # Check if it's a PPCOD/COD
    if sol.startswith('SOL'):
        r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['custom_order_type','custom_cod_amount']),
                    'limit_page_length': 1}, timeout=15)
        so_data = r_so.json().get('data', [])
        if so_data:
            atlas_type = so_data[0].get('custom_order_type', '') or ''
            atlas_cod = float(so_data[0].get('custom_cod_amount', 0) or 0)
            if atlas_type == 'PPCOD' or atlas_type == 'COD':
                order_type = 'COD'
                cod_value = atlas_cod
            print(f'  Atlas type: {atlas_type} | COD={atlas_cod}')

    # Use -R suffix to avoid cached AWB
    # Count how many cancelled DNs exist for this order
    ref_suffix = '-R1'
    ref = sol + ref_suffix

    print(f'  Customer: {cust} | PIN: {pin} | Weight: {total_weight_g}g | {order_type} COD={cod_value}')
    print(f'  Ref: {ref}')

    # Step 3: Create new Clickpost order
    print(f'  Step 3: Creating new Clickpost order...')
    cp_payload = {
        'pickup_info': {
            'pickup_name': 'WIN THE BUY BOX PVT LTD',
            'pickup_phone': '9573652101',
            'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
            'pickup_city': 'Hyderabad',
            'pickup_state': 'Telangana',
            'pickup_pincode': '501218',
            'pickup_country': 'IN',
            'email': 'hydwh@solara.in',
            'pickup_time': '2026-05-08T10:00:00Z',
        },
        'drop_info': {
            'drop_name': d.get('customer_name', ''),
            'drop_phone': phone,
            'drop_address': drop_address,
            'drop_city': addr_data.get('city', ''),
            'drop_state': addr_data.get('state', ''),
            'drop_pincode': pin,
            'drop_country': 'IN',
            'drop_email': addr_data.get('email_id', '') or 'noreply@solara.in',
        },
        'shipment_details': {
            'order_type': order_type,
            'invoice_value': grand_total,
            'reference_number': ref,
            'length': 30, 'breadth': 20, 'height': 15,
            'weight': total_weight_g,
            'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                       'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
            'delivery_type': 'FORWARD',
            'cod_value': cod_value,
            'courier_partner': 4,  # Delhivery
            'invoice_number': dn,
            'invoice_date': d.get('posting_date', ''),
        },
        'gst_info': {
            'seller_gstin': '36AAHCW1325Q1Z2',
            'taxable_value': float(d.get('net_total', 0) or 0),
            'ewaybill_serial_number': '',
            'is_seller_registered_under_gst': True,
            'place_of_supply': addr_data.get('state', ''),
            'cstin': '',
            'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
            'sgst_amount': 0, 'cgst_amount': 0,
            'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
            'invoice_number': dn, 'invoice_date': d.get('posting_date', ''), 'hsn_code': '',
        },
        'additional': {
            'label': True,
            'return_info': {
                'name': 'WIN THE BUY BOX PVT LTD',
                'phone': '9573652101',
                'address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'city': 'Hyderabad',
                'state': 'Telangana',
                'pincode': '501218',
                'country': 'IN',
            },
            'async': False,
        },
    }

    r_cp = requests.post(
        f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)

    cp_resp = r_cp.json()
    meta = cp_resp.get('meta', {})

    if meta.get('success') and meta.get('status') == 200:
        new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
        print(f'  NEW AWB={new_awb}')

        # Step 4: Save new AWB to DN
        sn = 'tmp_nawb_' + dn.replace('-', '_').lower()
        script = (
            "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + new_awb + "',update_modified=False)\n"
            "frappe.db.commit()\n"
            "frappe.response['message']='ok'"
        )
        msg = run_server_script(sn, script)
        if msg:
            print(f'  AWB saved to DN')

        # Step 5: Update Shopify tracking if fulfillment exists
        if shopify_oid:
            tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
            r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json',
                                 headers=SHOP_H, timeout=15)
            existing = r_ful.json().get('fulfillments', [])
            if existing:
                ful_id = str(existing[-1].get('id', ''))
                payload = {
                    'fulfillment': {
                        'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': 'Delhivery'},
                        'notify_customer': True,
                    }
                }
                r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                                    headers=SHOP_H, json=payload, timeout=15)
                if r_u.status_code in (200, 201):
                    print(f'  Shopify tracking updated on fulfillment {ful_id}')
                else:
                    print(f'  Shopify tracking update FAIL: {r_u.status_code} {r_u.text[:200]}')
            else:
                # Create new fulfillment
                r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json',
                                    headers=SHOP_H, timeout=15)
                fos = r_fo.json().get('fulfillment_orders', [])
                open_fos = []
                for fo in fos:
                    if fo.get('status') in ('open', 'in_progress'):
                        fo_items = []
                        for li in fo.get('line_items', []):
                            fq = li.get('fulfillable_quantity', 0)
                            if fq > 0:
                                fo_items.append({'id': li['id'], 'quantity': fq})
                        if fo_items:
                            open_fos.append({
                                'fulfillment_order_id': fo['id'],
                                'fulfillment_order_line_items': fo_items
                            })
                if open_fos:
                    payload = {
                        'fulfillment': {
                            'line_items_by_fulfillment_order': open_fos,
                            'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': 'Delhivery'},
                            'notify_customer': True,
                        }
                    }
                    r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json',
                                        headers=SHOP_H, json=payload, timeout=30)
                    if r_f.status_code in (200, 201):
                        sf_id = r_f.json().get('fulfillment', {}).get('id', '')
                        print(f'  Shopify fulfillment created: {sf_id}')
                    else:
                        print(f'  Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:200]}')
                else:
                    print(f'  No open FOs on Shopify')
        else:
            print(f'  No shopify_order_id (replacement) - skip Shopify sync')

        results.append((sol, 'OK', dn, old_awb, new_awb))
    else:
        err_msg = meta.get('message', '')
        print(f'  CLICKPOST CREATE FAIL: {err_msg}')
        print(f'  Full: {json.dumps(cp_resp)[:400]}')
        results.append((sol, 'FAIL', dn, old_awb, err_msg[:80]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('CANCEL + RECREATE SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  {r[0]}: OLD={r[3]} -> NEW={r[4]} on {r[2]}')
    else:
        print(f'  {r[0]}: FAIL {r[3]} | {r[4]}')
