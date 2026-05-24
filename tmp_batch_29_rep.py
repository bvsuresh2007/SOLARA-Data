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
        print(f'    Script error: {exc[:300]}')
        return None
    return msg

sos = [
    'REP-2627-SHP-00635', 'REP-2627-OTH-00050', 'REP-2627-SHP-00638',
    'REP-2627-SHP-00643', 'REP-2627-SHP-00618', 'REP-2627-SHP-00619',
    'REP-2627-SHP-00620', 'REP-2627-SHP-00629', 'REP-2627-SHP-00633',
    'REP-2627-SHP-00634', 'REP-2627-SHP-00636', 'REP-2627-SHP-00639',
    'REP-2627-SHP-00640', 'REP-2627-SHP-00641', 'REP-2627-SHP-00642',
    'REP-2627-SHP-00625', 'REP-2627-SHP-00626', 'REP-2627-SHP-00627',
    'REP-2627-SHP-00628', 'REP-2627-SHP-00630', 'REP-2627-SHP-00631',
    'REP-2627-SHP-00632', 'REP-2627-SHP-00621', 'REP-2627-SHP-00622',
    'REP-2627-SHP-00623', 'REP-2627-SHP-00624', 'REP-2627-OTH-00049',
    'REP-2627-SHP-00637', 'REP-2627-SHP-00644',
]

results = []

for idx, so_name in enumerate(sos, 1):
    print(f'\n{"="*60}')
    print(f'[{idx}/29] {so_name}')

    # Get SO details
    r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    if r.status_code != 200:
        print(f'  SO NOT FOUND')
        results.append((so_name, '', '', '', 'SO_NOT_FOUND'))
        continue
    so = r.json().get('data', {})
    addr_name = so.get('shipping_address_name', '')
    cust_name = so.get('customer_name', '')
    print(f'  {cust_name} | addr={addr_name}')

    if not addr_name:
        print(f'  NO SHIPPING ADDRESS on SO!')
        results.append((so_name, cust_name, '', '', 'NO_ADDR'))
        continue

    # Create DN from SO
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        results.append((so_name, cust_name, '', '', 'DN_MAKE_FAIL'))
        continue

    dn_draft = r_dn.json().get('message', {})
    dn_items = dn_draft.get('items', [])
    if not dn_items:
        print(f'  ERROR: No items in DN draft (per_delivered may be 100%)')
        results.append((so_name, cust_name, '', '', 'NO_ITEMS'))
        continue

    dn_draft['shipping_address_name'] = addr_name
    dn_draft['customer_address'] = addr_name
    dn_draft['is_replacement'] = 1

    # Fix taxes
    for tax in dn_draft.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    # Save DN
    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        print(f'  DN save failed: {r3.status_code} {r3.text[:300]}')
        results.append((so_name, cust_name, '', '', 'DN_SAVE_FAIL'))
        continue

    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

    # Submit DN
    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'  DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'  DN submitted (417 OK)!')
        else:
            print(f'  DN submit failed: {r4.text[:300]}')
            results.append((so_name, cust_name, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((so_name, cust_name, dn_name, '', 'DN_SUBMIT_FAIL'))
        continue

    # Check AWB (auto-trigger from Clickpost server script)
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')

    if awb:
        print(f'  AWB={awb} via {courier} (auto)')
        results.append((so_name, cust_name, dn_name, awb, courier))
    else:
        # Manual Clickpost AWB creation
        print(f'  No auto-AWB, creating manually...')
        r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
        dn_data = r_dn2.json().get('data', {})
        items_list = dn_data.get('items', [])
        grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
        net_total = float(dn_data.get('net_total', 0) or 0)
        total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)
        posting_date = dn_data.get('posting_date', '')

        r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
        addr = r_a.json().get('data', {})
        pin = str(addr.get('pincode', ''))
        drop_address = (str(addr.get('address_line1', '')) + ' ' + str(addr.get('address_line2', ''))).strip()
        phone = str(addr.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(phone) > 10: phone = phone[-10:]
        city = addr.get('city', '')
        state = addr.get('state', '')
        email = addr.get('email_id', '') or 'noreply@solara.in'

        new_awb = ''
        new_courier = ''
        for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
            cp_payload = {
                'pickup_info': {
                    'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                    'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                    'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-16T10:00:00Z',
                },
                'drop_info': {
                    'drop_name': cust_name, 'drop_phone': phone,
                    'drop_address': drop_address, 'drop_city': city,
                    'drop_state': state, 'drop_pincode': pin,
                    'drop_country': 'IN', 'drop_email': email,
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
                    'is_seller_registered_under_gst': True, 'place_of_supply': state,
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
            print(f'    Trying {cp_name}...')
            r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
            cp_resp = r_cp.json()
            meta = cp_resp.get('meta', {})
            if meta.get('success') and meta.get('status') == 200:
                new_awb = str(cp_resp.get('result', {}).get('waybill', ''))
                new_courier = cp_name
                print(f'    SUCCESS! AWB={new_awb} via {new_courier}')
                break
            else:
                err = meta.get('message', '')
                print(f'    FAIL {cp_name}: {err[:200]}')
                if 'already placed' in err.lower():
                    cp_payload['shipment_details']['reference_number'] = so_name + '-R1'
                    print(f'    Retrying with -R1...')
                    r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                    meta2 = r_cp2.json().get('meta', {})
                    if meta2.get('success') and meta2.get('status') == 200:
                        new_awb = str(r_cp2.json().get('result', {}).get('waybill', ''))
                        new_courier = cp_name
                        print(f'    SUCCESS with -R1! AWB={new_awb} via {new_courier}')
                        break

        if new_awb:
            script = (
                f"frappe.db.set_value('Delivery Note','{dn_name}','awb_number','{new_awb}',update_modified=False)\n"
                f"frappe.db.set_value('Delivery Note','{dn_name}','courier_partner','{new_courier}',update_modified=False)\n"
                f"frappe.db.commit()\n"
                f"frappe.response['message']='ok'"
            )
            msg = run_server_script(f'tmp_awb_{idx}', script)
            print(f'    DN AWB saved: {msg}')
            results.append((so_name, cust_name, dn_name, new_awb, new_courier))
        else:
            print(f'    ALL COURIERS FAILED')
            results.append((so_name, cust_name, dn_name, '', 'AWB_FAIL'))

# Summary
print(f'\n\n{"="*80}')
print('SUMMARY')
print(f'{"="*80}')
ok = 0
fail = 0
for so_name, cust, dn, awb, status in results:
    if awb and status not in ('DN_MAKE_FAIL', 'DN_SAVE_FAIL', 'DN_SUBMIT_FAIL', 'AWB_FAIL', 'NO_ADDR', 'NO_ITEMS', 'SO_NOT_FOUND'):
        print(f'  OK  {so_name:<25} {cust:<25} DN={dn:<18} AWB={awb:<18} {status}')
        ok += 1
    else:
        print(f'  FAIL {so_name:<25} {cust:<25} DN={dn:<18} {status}')
        fail += 1
print(f'\n  OK={ok} | FAIL={fail}')
