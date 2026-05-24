import os, requests, json
from dotenv import load_dotenv
load_dotenv()

CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

print("=== Test 7: courier_partner in shipment_details + fixed return_info ===")
p = {
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
        'drop_name': 'Test User',
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
        'reference_number': 'TEST-BD-V3-007',
        'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
        'items': [{'sku': 'SOL-INS-WB-201', 'description': 'test item', 'quantity': 1, 'price': 1549}],
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

r = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                   json=p, headers={'Content-Type': 'application/json'}, timeout=30)
print(f"Status: {r.status_code}")
print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
