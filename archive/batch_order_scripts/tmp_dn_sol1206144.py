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

so_name = 'SHP27-13868'
sol = 'SOL1206144'
shopify_oid = '7086773698792'
addr_name = 'Siddharth Singh-Shipping'

# Create DN from SO
r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
    headers=H, params={'source_name': so_name}, timeout=15)
dn_draft = r_dn.json().get('message', {})
dn_draft['shipping_address_name'] = addr_name
dn_draft['customer_address'] = addr_name
dn_draft['shopify_order_id'] = shopify_oid
dn_draft['shopify_order_number'] = sol
for tax in dn_draft.get('taxes', []):
    if tax.get('item_wise_tax_detail') is None:
        tax['item_wise_tax_detail'] = '{}'
for item in dn_draft.get('items', []):
    item.pop('item_tax_template', None)
for key in ['__islocal', '__unsaved', 'amended_from']:
    dn_draft.pop(key, None)

r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
if r3.status_code != 200:
    print(f'DN save failed: {r3.status_code} {r3.text[:400]}')
    sys.exit(1)

dn_name = r3.json().get('data', {}).get('name', '')
print(f'DN created: {dn_name}')

# Submit DN
r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
if r4.status_code == 200:
    print(f'DN submitted!')
elif r4.status_code == 417:
    time.sleep(2)
    r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
    if r5.json().get('data', {}).get('docstatus') == 1:
        print(f'DN submitted (417 OK)!')
    else:
        print(f'DN submit failed: {r4.text[:300]}')
        sys.exit(1)
else:
    print(f'DN submit failed: {r4.status_code} {r4.text[:300]}')
    sys.exit(1)

# Check AWB
time.sleep(3)
r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
    'fields': json.dumps(['awb_number', 'courier_partner'])
}, timeout=15)
d = r6.json().get('data', {})
awb = d.get('awb_number', '')
courier = d.get('courier_partner', '')
print(f'AWB={awb} | {courier}')

if not awb:
    print('No AWB from auto-trigger, creating manually...')
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr = r_a.json().get('data', {})
    pin = str(addr.get('pincode', ''))
    drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
    phone = str(addr.get('phone', ''))
    city = addr.get('city', '')
    state = addr.get('state', '')
    email_addr = addr.get('email_id', '') or 'noreply@solara.in'

    r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dn_data = r_dn2.json().get('data', {})
    items_list = dn_data.get('items', [])
    grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-15T10:00:00Z',
            },
            'drop_info': {
                'drop_name': 'Siddharth Singh', 'drop_phone': phone,
                'drop_address': drop_address, 'drop_city': city,
                'drop_state': state, 'drop_pincode': pin,
                'drop_country': 'IN', 'drop_email': email_addr,
            },
            'shipment_details': {
                'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': sol,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                'invoice_number': dn_name, 'invoice_date': dn_data.get('posting_date', ''),
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(dn_data.get('net_total', 0) or 0),
                'is_seller_registered_under_gst': True, 'place_of_supply': state,
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0,
                'igst_amount': float(dn_data.get('total_taxes_and_charges', 0) or 0),
                'invoice_number': dn_name, 'invoice_date': dn_data.get('posting_date', ''),
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
        print(f'Trying {cp_name}...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})
        if meta.get('success') and meta.get('status') == 200:
            awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cp_name
            print(f'SUCCESS! AWB={awb} via {courier}')
            script = "frappe.db.set_value('Delivery Note','" + dn_name + "','awb_number','" + awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + dn_name + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
            msg = run_server_script('tmp_awb_1206144', script)
            print(f'DN AWB saved: {msg}')
            break
        else:
            print(f'FAIL {cp_name}: {meta.get("message","")[:200]}')

# Sync to Shopify
if awb:
    tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
    r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
    fos = r_fo.json().get('fulfillment_orders', [])
    open_fos = [fo for fo in fos if fo.get('status') in ('open', 'in_progress')]
    if open_fos:
        line_items_by_fo = []
        for fo in open_fos:
            fo_lines = [{'id': li['id'], 'quantity': li['fulfillable_quantity']} for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
            if fo_lines:
                line_items_by_fo.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_lines})
        if line_items_by_fo:
            ful_payload = {
                'fulfillment': {
                    'line_items_by_fulfillment_order': line_items_by_fo,
                    'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                    'notify_customer': True,
                }
            }
            r_cf = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=ful_payload, timeout=30)
            print(f'Shopify fulfillment: {r_cf.status_code}')
            if r_cf.status_code in (200, 201):
                ful_id = r_cf.json().get('fulfillment', {}).get('id', '')
                time.sleep(1)
                payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': False}}
                requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                print(f'Shopify 2nd push done')
    else:
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        fuls = r_ful.json().get('fulfillments', [])
        if fuls:
            ful_id = str(fuls[-1].get('id', ''))
            payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'Shopify tracking updated: {r_u.status_code}')

print(f'\nDONE: {sol} | SO={so_name} | DN={dn_name} | AWB={awb} via {courier}')
