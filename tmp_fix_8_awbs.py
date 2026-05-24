import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'  Script create failed: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(6)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    if exc:
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

# Orders with their existing DNs and new Shopify addresses
# For MISMATCH ones, we need to update DN shipping_address_name
orders = [
    # (sol, so_name, dn, new_addr_name, old_awb, otype)
    ('SOL1205358', 'SHP27-11655', 'SHPDN27-14018', 'sindhu d-SOL1205358-Shipping', '', 'Prepaid'),
    ('SOL1200450', 'SHP27-06613', 'SHPDN27-12343', 'kapil . - 1-Shipping', '29044411222631', 'PPCOD'),
    ('SOL1202432', 'SHP27-08679', 'SHPDN27-12556', 'Rd Glarisa -Shipping-1', '', 'Prepaid'),
    ('SOL1202791', 'SHP27-09090', 'SHPDN27-12831', 'Seema Hipparkar-SOL1202791-Shipping', '', 'PPCOD'),
    ('SOL1202422', 'SHP27-08669', 'SHPDN27-14287', 'Shambhavi Binni-Shipping-2', '', 'PPCOD'),
    ('SOL1197981', 'SHP27-04151', 'SHPDN27-08662', 'Omkar singh-Shipping-1', '', 'Prepaid'),
    ('SOL1206214', 'SHP27-12514', 'SHPDN27-15632', 'DIVYA SINGH - 3-SOL1206214-Shipping', '', 'Prepaid'),
    ('SOL1205979', 'SHP27-12283', 'SHPDN27-15092', 'Anuradha Malik-SOL1205979-Shipping', '', 'Prepaid'),
]

# Step 1: Update shipping_address_name on mismatched DNs
mismatched = [
    ('SOL1200450', 'SHPDN27-12343', 'kapil . - 1-Shipping'),
    ('SOL1202432', 'SHPDN27-12556', 'Rd Glarisa -Shipping-1'),
    ('SOL1202422', 'SHPDN27-14287', 'Shambhavi Binni-Shipping-2'),
    ('SOL1197981', 'SHPDN27-08662', 'Omkar singh-Shipping-1'),
]

print("Step 1: Updating shipping addresses on mismatched DNs...")
lines = []
for sol, dn, new_addr in mismatched:
    lines.append(f"frappe.db.set_value('Delivery Note','{dn}','shipping_address_name','{new_addr}',update_modified=False)")
    lines.append(f"frappe.db.set_value('Delivery Note','{dn}','customer_address','{new_addr}',update_modified=False)")
lines.append("frappe.db.commit()")
lines.append("frappe.response['message']='ok'")
msg = run_server_script('tmp_upd_dn_addr', "\n".join(lines))
print(f"  Result: {msg}")

# Step 2: Cancel old AWB for SOL1200450
print("\nStep 2: Cancel old AWB for SOL1200450...")
r_cancel = requests.post('https://www.clickpost.in/api/v1/cancel-order/',
    params={'key': CP_KEY, 'username': 'solara'},
    json={'waybill': '29044411222631', 'cp_id': 4, 'cancellation_type': 'ORDER'},
    headers={'Content-Type': 'application/json'}, timeout=15)
print(f"  Cancel: {r_cancel.json().get('meta',{})}")

# Step 3: Create AWBs for all 8 (including SOL1202753 which already has AWB from earlier)
print("\nStep 3: Creating AWBs...")
results = []

for sol, so_name, dn, new_addr, old_awb, otype in orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} | {dn} ===')

    # Get DN details
    r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    d = r.json().get('data', {})
    shopify_oid = d.get('shopify_order_id', '')
    items_list = d.get('items', [])
    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    cod_amount = float(d.get('custom_cod_amount', 0) or 0)

    # Get the correct address (new Shopify one)
    r_a = requests.get(f'{BASE}/api/resource/Address/{new_addr}', headers=H, timeout=15)
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
    order_type_cp = 'COD' if otype == 'PPCOD' else 'PREPAID'
    cod_val = cod_amount if otype == 'PPCOD' else 0
    print(f'  {cust_name} | {city} {state} PIN={pin} | Ph={phone}')
    print(f'  Items: {items_str} | {order_type_cp} COD={cod_val}')

    # Create AWB
    ref = sol
    new_awb = ''
    courier = ''
    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-15T10:00:00Z',
            },
            'drop_info': {
                'drop_name': cust_name, 'drop_phone': phone,
                'drop_address': drop_address, 'drop_city': city,
                'drop_state': state, 'drop_pincode': pin,
                'drop_country': 'IN', 'drop_email': email,
            },
            'shipment_details': {
                'order_type': order_type_cp, 'invoice_value': grand_total, 'reference_number': ref,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_val, 'courier_partner': cp_id,
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
        print(f'  Trying {cp_name}...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})
        if meta.get('success') and meta.get('status') == 200:
            new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cp_name
            print(f'  SUCCESS! AWB={new_awb} via {courier}')
            break
        else:
            err = meta.get('message', '')
            print(f'  FAIL {cp_name}: {err[:200]}')
            if 'already placed' in err.lower():
                for suffix in ['-R1', '-R2', '-R3']:
                    cp_payload['shipment_details']['reference_number'] = sol + suffix
                    print(f'  Retrying with {suffix}...')
                    r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                    meta2 = r_cp2.json().get('meta', {})
                    if meta2.get('success') and meta2.get('status') == 200:
                        new_awb = str(r_cp2.json().get('result', {}).get('waybill', ''))
                        courier = cp_name
                        print(f'  SUCCESS with {suffix}! AWB={new_awb} via {courier}')
                        break
                    else:
                        print(f'  FAIL {suffix}: {meta2.get("message","")[:150]}')
                if new_awb:
                    break

    if not new_awb:
        print(f'  ALL COURIERS FAILED')
        results.append((sol, 'FAIL', dn, '', cust_name))
        continue

    # Save AWB to DN
    sn = f'tmp_awb_{dn.lower().replace("-","_")}'
    script = (
        f"frappe.db.set_value('Delivery Note','{dn}','awb_number','{new_awb}',update_modified=False)\n"
        f"frappe.db.set_value('Delivery Note','{dn}','courier_partner','{courier}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    print(f'  DN AWB saved: {msg}')

    # Update Shopify tracking
    if shopify_oid:
        tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        fuls = r_ful.json().get('fulfillments', [])
        if fuls:
            ful_id = str(fuls[-1].get('id', ''))
            payload = {'fulfillment': {'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'  Shopify tracking updated: {r_u.status_code}')
            time.sleep(1)
            r_u2 = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'  Shopify tracking 2nd push: {r_u2.status_code}')
        else:
            print(f'  No Shopify fulfillment to update')
    else:
        print(f'  No shopify_order_id on DN')

    results.append((sol, 'OK', dn, f'{new_awb} ({courier})', cust_name))
    time.sleep(0.5)

print(f'\n\n{"="*80}')
print('SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] != 'OK']
for r in ok:
    print(f'  OK   {r[0]} | {r[4]} | {r[2]} | {r[3]}')
for r in fail:
    print(f'  FAIL {r[0]} | {r[4]} | {r[2]}')
print(f'\n  Total: {len(ok)} OK | {len(fail)} failed')
# Don't forget SOL1202753 already done: SHPDN27-16131 AWB=29044411231215 Delhivery
print(f'\n  + SOL1202753 already done: SHPDN27-16131 AWB=29044411231215 Delhivery')
