import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# All 8 stuck DNs — try Bluedart for all
dns_to_fix = [
    ('SOL1202824', 'SHPDN27-10780', '201308', 'Ajay Singh', '9650037998'),
    ('SOL1202897', 'SHPDN27-10831', '201306', 'Preeti .', '9891700375'),
    ('SOL1202968', 'SHPDN27-10861', '600082', 'Jyothy .', '7200199992'),
    ('SOL1202978', 'SHPDN27-10765', '600019', 'Prem Kumar Vivekanandhan', '9551323900'),
    ('SOL1202852', 'SHPDN27-10799', '795001', 'Marina Rajkumari', '9774595068'),
    ('SOL1202984', 'SHPDN27-10865', '795001', 'Sellina .', '8131816989'),
    ('SOL1202999', 'SHPDN27-10671', '795001', 'Ranchui .', '9612111343'),
    ('SOL1203024', 'SHPDN27-10871', '737101', 'Angelina Namchu', '8250087769'),
]

# Step 1: Check Bluedart serviceability for all pincodes
pincodes = list(set([d[2] for d in dns_to_fix]))
print("=== BLUEDART SERVICEABILITY CHECK ===")
bd_ok = set()
for pin in sorted(pincodes):
    payload = [{
        'pickup_pincode': '501218',
        'drop_pincode': pin,
        'order_type': 'PREPAID',
        'reference_number': 'test',
        'item': 'test',
        'invoice_value': 1000,
        'delivery_type': 'FORWARD',
        'weight': 2000,
        'height': 15, 'length': 30, 'breadth': 20,
    }]
    try:
        r = requests.post(f'https://www.clickpost.in/api/v1/recommendation_api/?key={CP_KEY}',
                          json=payload, headers={'Content-Type': 'application/json'}, timeout=15)
        resp = r.json()
        if isinstance(resp, dict) and resp.get('meta', {}).get('success'):
            result = resp.get('result', [])
            if result and isinstance(result, list):
                prefs = result[0].get('preference_array', [])
                bd_found = False
                for p in prefs:
                    if p.get('cp_id') == 5:
                        bd_found = True
                        break
                if bd_found:
                    bd_ok.add(pin)
                    print(f"  PIN {pin}: BLUEDART OK")
                else:
                    cp_names = [p.get('cp_name','?') for p in prefs[:3]]
                    print(f"  PIN {pin}: NO BLUEDART (available: {cp_names})")
            else:
                print(f"  PIN {pin}: NOT SERVICEABLE by any courier")
        else:
            print(f"  PIN {pin}: API fail")
    except Exception as e:
        print(f"  PIN {pin}: ERROR {str(e)[:60]}")

# Step 2: For Bluedart-serviceable pincodes, create Clickpost shipments
print(f"\n=== CREATING BLUEDART AWBS ===")
print(f"Bluedart OK pincodes: {sorted(bd_ok)}")

results = []
for sol, dn, pin, customer, phone in dns_to_fix:
    print(f"\n--- {sol} {dn} PIN={pin} ---")

    if pin not in bd_ok:
        print(f"  SKIP - Bluedart not available for {pin}")
        results.append((sol, dn, 'NOT_SERVICEABLE', '', pin))
        continue

    # Get DN details for Clickpost payload
    try:
        r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
        d = r_dn.json().get('data', {})
    except:
        print(f"  DN fetch timeout")
        results.append((sol, dn, 'TIMEOUT', '', pin))
        continue

    addr_name = d.get('shipping_address_name', '')
    shopify_order_number = d.get('shopify_order_number', sol)

    # Get address
    addr_data = {}
    if addr_name:
        try:
            r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=30)
            addr_data = r_a.json().get('data', {})
        except:
            pass

    drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip() or 'Address'
    drop_city = addr_data.get('city', '') or 'City'
    drop_state = addr_data.get('state', '') or 'State'
    drop_pin = addr_data.get('pincode', pin)
    drop_phone = addr_data.get('phone', phone)
    drop_name = customer
    drop_email = addr_data.get('email_id', '') or 'noreply@solara.in'

    # Items for weight calc
    items_list = d.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0:
        total_weight = len(items_list) * 500
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200:
        total_weight_g = 500

    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    item_desc = ', '.join([str(it.get('item_code', '')) for it in items_list])

    # Check cancelled DNs for -R suffix
    r_cdns = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',shopify_order_number],['docstatus','=',2]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 20}, timeout=30)
    cancelled = r_cdns.json().get('data', [])
    ref = shopify_order_number
    if cancelled:
        ref = shopify_order_number + '-R' + str(len(cancelled))

    # Clickpost v3 payload
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
            'drop_name': drop_name,
            'drop_phone': drop_phone,
            'drop_address': drop_address,
            'drop_city': drop_city,
            'drop_state': drop_state,
            'drop_pincode': str(drop_pin),
            'drop_country': 'IN',
            'drop_email': drop_email,
        },
        'shipment_details': {
            'order_type': 'PREPAID',
            'invoice_value': grand_total,
            'reference_number': ref,
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
            'place_of_supply': drop_state,
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

    try:
        r_cp = requests.post(
            f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
    except Exception as e:
        print(f"  Clickpost error: {str(e)[:80]}")
        results.append((sol, dn, 'CP_ERROR', '', pin))
        continue

    meta = cp_resp.get('meta', {})
    if meta.get('success') and meta.get('status') == 200:
        awb = str(cp_resp.get('result', {}).get('waybill', ''))
        print(f"  AWB={awb} (Bluedart)")

        # Save AWB to DN via temp server script
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

        results.append((sol, dn, 'OK', awb, pin))
    else:
        err_msg = str(cp_resp.get('result', cp_resp.get('meta', {}).get('message', '')))[:150]
        print(f"  Clickpost FAIL: {err_msg}")
        results.append((sol, dn, 'CP_FAIL', '', pin + ' ' + err_msg))

    time.sleep(1)

# Summary
print(f"\n\n{'='*90}")
print(f"SUMMARY")
print(f"{'='*90}")
ok = [r for r in results if r[2] == 'OK']
ns = [r for r in results if r[2] == 'NOT_SERVICEABLE']
fail = [r for r in results if r[2] not in ('OK', 'NOT_SERVICEABLE')]
print(f"OK: {len(ok)} | Not serviceable: {len(ns)} | Failed: {len(fail)}")
for sol, dn, status, awb, extra in results:
    if status == 'OK':
        print(f"  {sol} {dn} AWB={awb} Bluedart PIN={extra}")
    else:
        print(f"  {sol} {dn} {status} {extra}")
