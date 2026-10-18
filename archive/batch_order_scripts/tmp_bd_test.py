import os, requests, json
from dotenv import load_dotenv
load_dotenv()

CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# Minimal test payload - try different cp_id placements
base = {
    'pickup_info': {
        'pickup_name': 'WIN THE BUY BOX PVT LTD',
        'pickup_phone': '9573652101',
        'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village',
        'pickup_city': 'Hyderabad',
        'pickup_state': 'Telangana',
        'pickup_pincode': '501218',
        'pickup_country': 'IN',
        'email': 'hydwh@solara.in',
    },
    'drop_info': {
        'drop_name': 'Test',
        'drop_phone': '9650037998',
        'drop_address': 'A-903 JM florence Techzone',
        'drop_city': 'NOIDA',
        'drop_state': 'Uttar Pradesh',
        'drop_pincode': '201308',
        'drop_country': 'IN',
        'drop_email': 'noreply@solara.in',
    },
    'shipment_details': {
        'order_type': 'PREPAID',
        'invoice_value': 1549,
        'reference_number': 'TEST-BD-001',
        'length': 30,
        'breadth': 20,
        'height': 15,
        'weight': 500,
        'items': [{'sku': 'SOL-INS-WB-201', 'description': 'test', 'quantity': 1, 'price': 1549}],
        'delivery_type': 'FORWARD',
        'cod_value': 0,
    },
    'gst_info': {
        'seller_gstin': '36AAHCW1325Q1Z2',
        'taxable_value': 1313,
        'ewaybill_serial_number': '',
        'is_seller_registered_under_gst': True,
        'place_of_supply': 'Uttar Pradesh',
        'cstin': '',
        'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
        'sgst_amount': 0, 'cgst_amount': 0, 'igst_amount': 236,
        'invoice_number': 'TEST-001', 'invoice_date': '2026-05-04', 'hsn_code': '',
    },
    'additional': {
        'label': True,
        'return_info': {
            'return_name': 'WIN THE BUY BOX PVT LTD',
            'return_phone': '9573652101',
            'return_address': 'SY NO.68/1/E, Hamedullah Nagar Village',
            'return_city': 'Hyderabad',
            'return_state': 'Telangana',
            'return_pincode': '501218',
            'return_country': 'IN',
        },
        'async': False,
    },
}

# Test 1: cp_id at top level
print("=== Test 1: cp_id at top level ===")
p1 = {**base, 'cp_id': 5}
r1 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=p1, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  {r1.json()}")

# Test 2: cp_id inside shipment_details
print("\n=== Test 2: cp_id inside shipment_details ===")
p2 = dict(base)
p2['shipment_details'] = {**base['shipment_details'], 'cp_id': 5}
p2['shipment_details']['reference_number'] = 'TEST-BD-002'
r2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=p2, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  {r2.json()}")

# Test 3: No cp_id (let Clickpost choose)
print("\n=== Test 3: No cp_id (auto) ===")
p3 = dict(base)
p3['shipment_details'] = {**base['shipment_details'], 'reference_number': 'TEST-BD-003'}
r3 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=p3, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  {r3.json()}")
