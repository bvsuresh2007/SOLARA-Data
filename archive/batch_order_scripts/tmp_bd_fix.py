import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# 4 Bluedart-serviceable stuck DNs
dns_to_fix = [
    ('SOL1202824', 'SHPDN27-10780', '201308'),
    ('SOL1202897', 'SHPDN27-10831', '201306'),
    ('SOL1202968', 'SHPDN27-10861', '600082'),
    ('SOL1202978', 'SHPDN27-10765', '600019'),
]

results = []
for sol, dn, pin in dns_to_fix:
    print(f"\n=== {sol} {dn} PIN={pin} ===")

    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=45)
    d = r_dn.json().get('data', {})

    addr_name = d.get('shipping_address_name', '')
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=30)
    addr_data = r_a.json().get('data', {})

    drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip() or 'Address'
    items_list = d.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0:
        total_weight = len(items_list) * 500
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200:
        total_weight_g = 500

    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)

    # Use -BD suffix to avoid collision with existing Delhivery order
    ref = sol + '-BD'

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
            'drop_name': d.get('customer_name', ''),
            'drop_phone': str(addr_data.get('phone', '')),
            'drop_address': drop_address,
            'drop_city': addr_data.get('city', ''),
            'drop_state': addr_data.get('state', ''),
            'drop_pincode': str(pin),
            'drop_country': 'IN',
            'drop_email': addr_data.get('email_id', '') or 'noreply@solara.in',
        },
        'shipment_details': {
            'order_type': 'PREPAID',
            'invoice_value': grand_total,
            'reference_number': ref,
            'length': 30,
            'breadth': 20,
            'height': 15,
            'weight': total_weight_g,
            'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100], 'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
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

    print(f"  Ref: {ref} | Weight: {total_weight_g}g | Total: Rs{grand_total}")

    r_cp = requests.post(
        f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)

    try:
        cp_resp = r_cp.json()
    except:
        print(f"  Bad response: {r_cp.text[:200]}")
        results.append((sol, dn, 'BAD_RESP', ''))
        continue

    print(f"  Response: {json.dumps(cp_resp)[:300]}")

    meta = cp_resp.get('meta', {})
    if meta.get('success') and meta.get('status') == 200:
        awb = str(cp_resp.get('result', {}).get('waybill', ''))
        print(f"  AWB={awb} Bluedart")

        # Save to DN
        sn = 'tmp_awb_' + dn.replace('-', '_').lower()
        script = (
            "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + awb + "',update_modified=False)\n"
            "frappe.db.set_value('Delivery Note','" + dn + "','courier_partner','Bluedart',update_modified=False)\n"
            "frappe.db.commit()\n"
            "frappe.response['message']='ok'"
        )
        r_ts = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
            json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
        if r_ts.status_code == 200:
            requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
            requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
            print(f"  Saved to DN")
        results.append((sol, dn, 'OK', awb))
    else:
        err = meta.get('message', '')
        print(f"  FAIL: {err}")
        results.append((sol, dn, 'FAIL', err[:100]))

    time.sleep(1)

print(f"\n{'='*80}")
print(f"SUMMARY")
for sol, dn, status, extra in results:
    print(f"  {sol} {dn} {status} {extra}")
