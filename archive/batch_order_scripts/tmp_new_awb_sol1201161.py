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
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

sol = 'SOL1201161'
dn = 'SHPDN27-07724'
shopify_oid = '7045280628968'

# Get address
r_a = requests.get(f'{BASE}/api/resource/Address/Ashish Choudhury-Shipping', headers=H, timeout=15)
addr = r_a.json().get('data', {})
pin = str(addr.get('pincode', ''))
drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
if len(phone) > 10: phone = phone[-10:]
city = addr.get('city', '')
state = addr.get('state', '')
email = addr.get('email_id', '') or 'noreply@solara.in'
name_c = addr.get('address_title', '')
print(f'Address: {name_c} | {drop_address} | {city} {state} {pin} | Phone: {phone}')

# Get DN items
r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
dn_full = r_dn.json().get('data', {})
items_list = dn_full.get('items', [])
total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
if total_weight <= 0: total_weight = len(items_list) * 0.5
total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
if total_weight_g < 200: total_weight_g = 500
grand_total = max(float(dn_full.get('grand_total', 0) or 0), 1.0)

items_str = ', '.join([it.get('item_code','') + ' x' + str(int(it.get('qty',1))) for it in items_list])
print(f'Items: {items_str} | Weight: {total_weight_g}g | Total: {grand_total}')

ref = sol + '-R2'
print(f'Reference: {ref}')

# Try Delhivery first (4), then Bluedart (5)
new_awb = ''
courier = ''
for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
    cp_payload = {
        'pickup_info': {
            'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
            'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
            'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
            'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-12T10:00:00Z',
        },
        'drop_info': {
            'drop_name': name_c, 'drop_phone': phone,
            'drop_address': drop_address, 'drop_city': city,
            'drop_state': state, 'drop_pincode': pin,
            'drop_country': 'IN', 'drop_email': email,
        },
        'shipment_details': {
            'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': ref,
            'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
            'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                       'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
            'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
            'invoice_number': dn, 'invoice_date': dn_full.get('posting_date', ''),
        },
        'gst_info': {
            'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(dn_full.get('net_total', 0) or 0),
            'is_seller_registered_under_gst': True, 'place_of_supply': state,
            'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
            'sgst_amount': 0, 'cgst_amount': 0,
            'igst_amount': float(dn_full.get('total_taxes_and_charges', 0) or 0),
            'invoice_number': dn, 'invoice_date': dn_full.get('posting_date', ''),
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
    print(f'\nTrying {cp_name}...')
    r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
    cp_resp = r_cp.json()
    meta = cp_resp.get('meta', {})
    if meta.get('success') and meta.get('status') == 200:
        new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
        courier = cp_name
        print(f'SUCCESS! AWB={new_awb} via {courier}')
        break
    else:
        print(f'FAIL {cp_name}: {meta.get("message","")[:200]}')

if not new_awb:
    print('\nALL COURIERS FAILED')
    sys.exit(1)

# Save AWB to DN
sn = 'tmp_nawb_shpdn27_07724'
script = "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + new_awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + dn + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
msg = run_server_script(sn, script)
print(f'DN AWB saved: {msg}')

# Shopify tracking update
tracking_url = f'https://www.clickpost.in/tracking/#/{new_awb}'
r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
fuls = r_ful.json().get('fulfillments', [])
if fuls:
    ful_id = str(fuls[-1].get('id', ''))
    payload = {'fulfillment': {'tracking_info': {'number': new_awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
    r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
    print(f'Shopify tracking updated: {r_u.status_code}')
    time.sleep(1)
    r_u2 = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
    print(f'Shopify tracking 2nd push: {r_u2.status_code}')
else:
    print('No existing fulfillment to update')

print(f'\nDONE: {sol} | New AWB={new_awb} via {courier}')
