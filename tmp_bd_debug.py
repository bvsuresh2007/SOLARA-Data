import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# Test with one DN - SOL1202824 SHPDN27-10780 PIN=201308
dn = 'SHPDN27-10780'
sol = 'SOL1202824'

r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=45)
d = r_dn.json().get('data', {})

addr_name = d.get('shipping_address_name', '')
r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=30)
addr_data = r_a.json().get('data', {})

drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip()
items_list = d.get('items', [])
total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
if total_weight <= 0:
    total_weight = len(items_list) * 500
total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
if total_weight_g < 200:
    total_weight_g = 500

grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)

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
    },
    'drop_info': {
        'drop_name': 'Ajay Singh',
        'drop_phone': '9650037998',
        'drop_address': drop_address,
        'drop_city': addr_data.get('city', ''),
        'drop_state': addr_data.get('state', ''),
        'drop_pincode': '201308',
        'drop_country': 'IN',
        'drop_email': 'noreply@solara.in',
    },
    'shipment_details': {
        'order_type': 'PREPAID',
        'invoice_value': grand_total,
        'reference_number': sol,
        'length': 30,
        'breadth': 20,
        'height': 15,
        'weight': total_weight_g,
        'items': [{'sku': it.get('item_code',''), 'description': it.get('item_name','')[:100], 'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
        'delivery_type': 'FORWARD',
        'cod_value': 0,
    },
    'gst_info': {
        'seller_gstin': '36AAHCW1325Q1Z2',
        'taxable_value': float(d.get('net_total', 0) or 0),
        'ewaybill_serial_number': '',
        'is_seller_registered_under_gst': True,
        'place_of_supply': addr_data.get('state', ''),
        'cstin': '',
        'sgst_tax_rate': 0,
        'cgst_tax_rate': 0,
        'igst_tax_rate': 18,
        'sgst_amount': 0,
        'cgst_amount': 0,
        'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
        'invoice_number': dn,
        'invoice_date': d.get('posting_date', ''),
        'hsn_code': '',
    },
    'additional': {
        'label': True,
        'return_info': {
            'return_name': 'WIN THE BUY BOX PVT LTD',
            'return_phone': '9573652101',
            'return_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
            'return_city': 'Hyderabad',
            'return_state': 'Telangana',
            'return_pincode': '501218',
            'return_country': 'IN',
        },
        'async': False,
    },
    'cp_id': 5,
}

print(f"Payload weight: {total_weight_g}g")
print(f"Grand total: {grand_total}")
print(f"Ref: {sol}")
print(f"Drop: {drop_address[:60]} PIN={addr_data.get('pincode','')} City={addr_data.get('city','')}")

r_cp = requests.post(
    f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
    json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)

print(f"\nClickpost status: {r_cp.status_code}")
print(f"Full response: {json.dumps(r_cp.json(), indent=2)[:1000]}")
