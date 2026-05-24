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

CUST = 'Crossword Bookstores Pvt Ltd'
COMPANY = 'Win The Buy Box Private Limited'

# Step 1: Create Address
addr_name = 'Crossword Bookstores Pvt Ltd-Sample-Sathish-Shipping'
addr_payload = {
    'name': addr_name,
    'address_title': CUST,
    'address_type': 'Shipping',
    'address_line1': 'Office no. 603-608, 6th Floor, Shorab Hall, Opp Jahangir Hospital',
    'address_line2': 'Behind Pune Railway Station',
    'city': 'Pune',
    'state': 'Maharashtra',
    'pincode': '411001',
    'country': 'India',
    'phone': '7358182070',
    'email_id': 'noreply@solara.in',
    'is_shipping_address': 1,
    'links': [{'link_doctype': 'Customer', 'link_name': CUST}],
}
r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
if r_ae.status_code == 200:
    r_au = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
    addr_name = r_au.json().get('data', {}).get('name', addr_name) if r_au.status_code == 200 else addr_name
    print(f'Address updated: {addr_name}')
else:
    r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_ac.status_code == 200:
        addr_name = r_ac.json().get('data', {}).get('name', addr_name)
        print(f'Address created: {addr_name}')
    else:
        print(f'Address create failed: {r_ac.status_code} {r_ac.text[:300]}')

# Step 2: Create SO
so_payload = {
    'naming_series': 'OTH-SAM2627-.#####',
    'customer': CUST,
    'transaction_date': '2026-05-17',
    'delivery_date': '2026-05-20',
    'company': COMPANY,
    'order_type': 'Sales',
    'currency': 'INR',
    'selling_price_list': 'Standard Selling',
    'customer_address': addr_name,
    'shipping_address_name': addr_name,
    'cost_center': 'Offline - WTBBPL',
    'custom_order_type': 'Prepaid',
    'items': [{
        'item_code': 'SOL-INS-WB-405',
        'qty': 1,
        'rate': 1,
        'delivery_date': '2026-05-20',
        'warehouse': 'Main Warehouse - WTBBPL',
    }],
}
r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
if r_so.status_code != 200:
    print(f'SO create failed: {r_so.status_code} {r_so.text[:400]}')
    sys.exit(1)
so_name = r_so.json().get('data', {}).get('name', '')
print(f'SO created: {so_name}')

r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
if r_sub.status_code == 200:
    print('SO submitted!')
else:
    print(f'SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
    sys.exit(1)

# Step 3: Create DN
r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
    headers=H, params={'source_name': so_name}, timeout=15)
dn_draft = r_dn.json().get('message', {})
dn_draft['shipping_address_name'] = addr_name
dn_draft['customer_address'] = addr_name
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

r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
if r4.status_code == 200:
    print('DN submitted!')
elif r4.status_code == 417:
    time.sleep(2)
    r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
    if r5.json().get('data', {}).get('docstatus') == 1:
        print('DN submitted (417 OK)!')
    else:
        print(f'DN submit failed: {r4.text[:300]}')
        sys.exit(1)
else:
    print(f'DN submit failed: {r4.status_code} {r4.text[:300]}')
    sys.exit(1)

# Step 4: Check AWB
time.sleep(3)
r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
    'fields': json.dumps(['awb_number', 'courier_partner'])
}, timeout=15)
d = r6.json().get('data', {})
awb = d.get('awb_number', '')
courier = d.get('courier_partner', '')

if not awb:
    print('No auto-AWB, creating manually...')
    r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dn_data = r_dn2.json().get('data', {})
    items_list = dn_data.get('items', [])
    grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
    posting_date = dn_data.get('posting_date', '')
    net_total = float(dn_data.get('net_total', 0) or 0)
    total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-17T10:00:00Z',
            },
            'drop_info': {
                'drop_name': 'Sathish', 'drop_phone': '7358182070',
                'drop_address': 'Office no. 603-608, 6th Floor, Shorab Hall, Opp Jahangir Hospital, Behind Pune Railway Station',
                'drop_city': 'Pune', 'drop_state': 'Maharashtra', 'drop_pincode': '411001',
                'drop_country': 'IN', 'drop_email': 'noreply@solara.in',
            },
            'shipment_details': {
                'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': so_name,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                'invoice_number': dn_name, 'invoice_date': posting_date,
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': net_total,
                'is_seller_registered_under_gst': True, 'place_of_supply': 'Maharashtra',
                'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                'sgst_amount': 0, 'cgst_amount': 0, 'igst_amount': total_taxes,
                'invoice_number': dn_name, 'invoice_date': posting_date,
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
            awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cp_name
            print(f'  SUCCESS! AWB={awb} via {courier}')
            break
        else:
            print(f'  FAIL {cp_name}: {meta.get("message","")[:200]}')

    if awb:
        script = (
            f"frappe.db.set_value('Delivery Note','{dn_name}','awb_number','{awb}',update_modified=False)\n"
            f"frappe.db.set_value('Delivery Note','{dn_name}','courier_partner','{courier}',update_modified=False)\n"
            f"frappe.db.commit()\n"
            f"frappe.response['message']='ok'"
        )
        msg = run_server_script('tmp_awb_cw', script)
        print(f'  DN AWB saved: {msg}')

print(f'\nDONE: SO={so_name} | DN={dn_name} | AWB={awb} via {courier}')
