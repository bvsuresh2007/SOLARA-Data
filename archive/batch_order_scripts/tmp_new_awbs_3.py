import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200: return None
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

orders = [
    ('REP-2627-SHP-00402', 'SHPDN27-06854'),
    ('REP-2627-SHP-00496', 'SHPDN27-11997'),
    ('REP-2627-SHP-00407', 'SHPDN27-06838'),
]

for so, dn in orders:
    print(f'\n{"="*60}')
    print(f'=== {so} / {dn} ===')

    r = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
    d = r.json().get('data', {})
    addr_name = d.get('shipping_address_name', '')
    items_list = d.get('items', [])
    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    cust_name = d.get('customer_name', '')
    posting_date = d.get('posting_date', '')
    net_total = float(d.get('net_total', 0) or 0)
    total_taxes = float(d.get('total_taxes_and_charges', 0) or 0)

    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr = r_a.json().get('data', {})
    pin = str(addr.get('pincode', ''))
    drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
    phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10: phone = phone[-10:]
    city = addr.get('city', '')
    state = addr.get('state', '')
    email = addr.get('email_id', '') or 'noreply@solara.in'
    print(f'  {cust_name} | {city} {state} PIN={pin} | Ph={phone}')

    # Use -R1 suffix since old AWB was cancelled (ref already used)
    ref_number = so + '-R1'
    print(f'  Ref: {ref_number}')

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
                'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': ref_number,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                'invoice_number': dn, 'invoice_date': posting_date,
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': net_total,
                'is_seller_registered_under_gst': True, 'place_of_supply': state,
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0, 'igst_amount': total_taxes,
                'invoice_number': dn, 'invoice_date': posting_date,
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
                cp_payload['shipment_details']['reference_number'] = ref_number + '-R2'
                print(f'  Retrying with -R2...')
                r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                meta2 = r_cp2.json().get('meta', {})
                if meta2.get('success') and meta2.get('status') == 200:
                    new_awb = str(r_cp2.json().get('result', {}).get('waybill', ''))
                    courier = cp_name
                    print(f'  SUCCESS with -R2! AWB={new_awb} via {courier}')
                    break

    if new_awb:
        script = (
            f"frappe.db.set_value('Delivery Note','{dn}','awb_number','{new_awb}',update_modified=False)\n"
            f"frappe.db.set_value('Delivery Note','{dn}','courier_partner','{courier}',update_modified=False)\n"
            f"frappe.db.commit()\n"
            f"frappe.response['message']='ok'"
        )
        msg = run_server_script(f'tmp_awb_{so[-3:]}', script)
        print(f'  DN AWB saved: {msg}')
    else:
        print(f'  ALL COURIERS FAILED')

print(f'\n{"="*60}')
print('DONE')
