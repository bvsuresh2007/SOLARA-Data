import os, requests, json
from dotenv import load_dotenv
load_dotenv()

CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# Test 4: v2 flat format
print("=== Test 4: v2 flat format ===")
p4 = {
    'key': CP_KEY,
    'username': 'solara',
    'pickup_name': 'WIN THE BUY BOX PVT LTD',
    'pickup_phone': '9573652101',
    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village',
    'pickup_city': 'Hyderabad',
    'pickup_state': 'Telangana',
    'pickup_pincode': '501218',
    'pickup_country': 'IN',
    'drop_name': 'Test',
    'drop_phone': '9650037998',
    'drop_address': 'A-903 JM florence Techzone',
    'drop_city': 'NOIDA',
    'drop_state': 'Uttar Pradesh',
    'drop_pincode': '201308',
    'drop_country': 'IN',
    'order_type': 'PREPAID',
    'invoice_value': 1549,
    'reference_number': 'TEST-BD-V2-001',
    'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
    'delivery_type': 'FORWARD',
    'cod_value': 0,
    'cp_id': 5,
    'email': 'hydwh@solara.in',
    'items': json.dumps([{'sku': 'SOL-INS-WB-201', 'description': 'test', 'quantity': 1, 'price': 1549}]),
}
r4 = requests.post(f'https://www.clickpost.in/api/v2/create-order/',
                    json=p4, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  Status: {r4.status_code}")
try:
    print(f"  {r4.json()}")
except:
    print(f"  {r4.text[:300]}")

# Test 5: v3 with courier_partner field
print("\n=== Test 5: v3 with courier_partner=5 ===")
p5 = {
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
        'reference_number': 'TEST-BD-V3-005',
        'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
        'items': [{'sku': 'SOL-INS-WB-201', 'description': 'test', 'quantity': 1, 'price': 1549}],
        'delivery_type': 'FORWARD',
        'cod_value': 0,
        'courier_partner': 5,
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
    'cp_id': 5,
}
r5 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                    json=p5, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  {r5.json()}")

# Test 6: v1 format
print("\n=== Test 6: v1 format ===")
p6 = {
    'pickup_name': 'WIN THE BUY BOX PVT LTD',
    'pickup_phone': '9573652101',
    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village',
    'pickup_city': 'Hyderabad',
    'pickup_state': 'Telangana',
    'pickup_pincode': '501218',
    'pickup_country': 'IN',
    'drop_name': 'Test',
    'drop_phone': '9650037998',
    'drop_address': 'A-903 JM florence Techzone',
    'drop_city': 'NOIDA',
    'drop_state': 'Uttar Pradesh',
    'drop_pincode': '201308',
    'drop_country': 'IN',
    'order_type': 'PREPAID',
    'invoice_value': 1549,
    'reference_number': 'TEST-BD-V1-006',
    'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
    'delivery_type': 'FORWARD',
    'cod_value': 0,
    'cp_id': 5,
    'email': 'hydwh@solara.in',
    'items': [{'sku': 'SOL-INS-WB-201', 'description': 'test', 'quantity': 1, 'price': 1549}],
}
r6 = requests.post(f'https://www.clickpost.in/api/v1/create-order/?username=solara&key={CP_KEY}',
                    json=p6, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"  Status: {r6.status_code}")
try:
    print(f"  {r6.json()}")
except:
    print(f"  {r6.text[:300]}")
