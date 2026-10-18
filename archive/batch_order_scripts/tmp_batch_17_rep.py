import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

sos = [
    'REP-2627-SHP-00648','REP-2627-SHP-00649','REP-2627-SHP-00661','REP-2627-SHP-00663',
    'REP-2627-SHP-00664','REP-2627-SHP-00650','REP-2627-SHP-00654','REP-2627-SHP-00655',
    'REP-2627-SHP-00656','REP-2627-SHP-00657','REP-2627-SHP-00658','REP-2627-SHP-00659',
    'REP-2627-SHP-00660','REP-2627-AMA-00028','REP-2627-SHP-00647','REP-2627-AMA-00029',
    'REP-2627-SHP-00197',
]

# REP-2627-SHP-00197 has a cancelled DN, so needs -R1 suffix for Clickpost
cancelled_dns_count = {'REP-2627-SHP-00197': 1}

results = []

for so_name in sos:
    print(f'\n=== {so_name} ===')

    # Step 1: Get SO details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    if r_so.status_code != 200:
        print(f'  SO fetch failed: {r_so.status_code}')
        results.append((so_name, '', '', '', 'SO_FETCH_FAIL'))
        continue
    so = r_so.json().get('data', {})
    cust = so.get('customer_name', '')
    addr = so.get('shipping_address_name', '')
    cust_addr = so.get('customer_address', '')

    # Step 2: Create DN from SO
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        results.append((so_name, cust, '', '', 'MAKE_DN_FAIL'))
        continue
    dn_draft = r_dn.json().get('message', {})

    # Set replacement fields
    dn_draft['is_replacement'] = 1
    dn_draft['shipping_address_name'] = addr
    dn_draft['customer_address'] = cust_addr or addr

    # Tax fixes
    for tax in dn_draft.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        print(f'  DN save failed: {r3.status_code} {r3.text[:300]}')
        results.append((so_name, cust, '', '', 'DN_SAVE_FAIL'))
        continue
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

    # Step 3: Submit DN
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
            results.append((so_name, cust, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((so_name, cust, dn_name, '', 'DN_SUBMIT_FAIL'))
        continue

    # Step 4: Check auto-AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''

    if awb:
        print(f'  Auto-AWB: {awb} via {courier}')
        results.append((so_name, cust, dn_name, awb, courier))
        continue

    # Step 5: Manual Clickpost
    print(f'  No auto-AWB, trying Clickpost manually...')
    r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dn_data = r_dn2.json().get('data', {})
    items_list = dn_data.get('items', [])
    grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
    posting_date = dn_data.get('posting_date', '')
    net_total = float(dn_data.get('net_total', 0) or 0)
    total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)

    # Get shipping address details
    r_addr = requests.get(f'{BASE}/api/resource/Address/{addr}', headers=H, timeout=15)
    addr_data = r_addr.json().get('data', {}) if r_addr.status_code == 200 else {}
    drop_name = cust
    drop_phone = str(addr_data.get('phone', '') or '')
    drop_addr1 = str(addr_data.get('address_line1', '') or '')
    drop_addr2 = str(addr_data.get('address_line2', '') or '')
    drop_address = f'{drop_addr1}, {drop_addr2}'.strip(', ') if drop_addr2 else drop_addr1
    drop_city = str(addr_data.get('city', '') or '')
    drop_state = str(addr_data.get('state', '') or '')
    drop_pin = str(addr_data.get('pincode', '') or '')
    drop_email = str(addr_data.get('email_id', '') or 'noreply@solara.in')

    # Reference number with -R suffix if needed
    ref = so_name
    cancel_count = cancelled_dns_count.get(so_name, 0)
    if cancel_count > 0:
        ref = f'{so_name}-R{cancel_count}'

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-19T10:00:00Z',
            },
            'drop_info': {
                'drop_name': drop_name, 'drop_phone': drop_phone,
                'drop_address': drop_address,
                'drop_city': drop_city, 'drop_state': drop_state, 'drop_pincode': drop_pin,
                'drop_country': 'IN', 'drop_email': drop_email,
            },
            'shipment_details': {
                'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': ref,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                'invoice_number': dn_name, 'invoice_date': posting_date,
            },
            'gst_info': {
                'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': net_total,
                'is_seller_registered_under_gst': True, 'place_of_supply': drop_state,
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
            awb = str(cp_resp.get('result', {}).get('waybill', ''))
            courier = cp_name
            print(f'    SUCCESS! AWB={awb} via {courier}')
            break
        else:
            print(f'    FAIL {cp_name}: {meta.get("message","")[:200]}')

    if awb:
        # Save AWB to DN via direct API update (try set_value approach)
        upd = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
            json={'awb_number': awb, 'courier_partner': courier}, timeout=15)
        if upd.status_code == 200:
            print(f'    AWB saved to DN')
        else:
            print(f'    AWB save via PUT failed ({upd.status_code}), will need server script')
        results.append((so_name, cust, dn_name, awb, courier))
    else:
        print(f'    NO AWB - both couriers failed')
        results.append((so_name, cust, dn_name, '', 'NO_AWB'))

print('\n\n========== SUMMARY ==========')
for so_name, cust, dn, awb, status in results:
    print(f'{so_name} | {cust[:25]:25s} | {dn:20s} | {awb or "NO AWB":20s} | {status}')
