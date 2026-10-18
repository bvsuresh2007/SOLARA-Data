import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r_tok = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={
    'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password',
}, timeout=30)
SHOPIFY_TOKEN = r_tok.json().get('message', '')
STORE = 'dev-solara.myshopify.com'
SH = {'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json'}

results = []

# PPCOD COD amounts
PPCOD_COD = {'SOL1209324': 2999.0, 'SOL1208589': 2999.0}

# Blank item_code SOs → correct Shopify SKU
BLANK_SKU_FIX = {
    'SOL1208766': [{'sku': 'SOL-CI-DT-103-FP-103', 'qty': 1, 'price': 1999}, {'sku': 'SOL-CKW-WSPA-101', 'qty': 1, 'price': 299}],
    'SOL1208644': [{'sku': 'SOL-CI-DT-103-FP-103', 'qty': 1, 'price': 1999}, {'sku': 'SOL-CKW-WSPA-101', 'qty': 1, 'price': 299}],
    'SOL1206392': [{'sku': 'SOL-CI-DT-103-FP-103', 'qty': 1, 'price': 1999}, {'sku': 'SOL-CKW-WSPA-101', 'qty': 1, 'price': 299}],
}

orders_to_process = [
    ('SOL1209524', 'SHP27-15785', ['SHPDN27-18868']),
    ('SOL1209350', 'SHP27-15615', ['SHPDN27-18513']),
    ('SOL1209229', 'SHP27-15497', ['SHPDN27-18625']),
    ('SOL1209146', 'SHP27-15415', ['SHPDN27-18661']),
    ('SOL1209066', 'SHP27-15337', ['SHPDN27-18248']),
    ('SOL1208766', 'SHP27-15040', []),  # blank item_code, no DN
    ('SOL1208644', 'SHP27-14918', []),  # blank item_code, no DN
    ('SOL1209324', 'SHP27-15590', ['SHPDN27-18709']),  # PPCOD
    ('SOL1208589', 'SHP27-14866', ['SHPDN27-18136']),  # PPCOD
    ('SOL1208639', 'SHP27-14913', ['SHPDN27-18023']),
    ('SOL1208612', 'SHP27-14888', ['SHPDN27-18106']),
    ('SOL1208513', 'SHP27-14792', ['SHPDN27-17669', 'SHPDN27-17674']),
    ('SOL1208108', 'SHP27-14395', ['SHPDN27-17396', 'SHPDN27-17395']),
    ('SOL1208078', 'SHP27-14365', ['SHPDN27-17420']),
    ('SOL1207824', 'SHP27-14114', ['SHPDN27-16994']),
    ('SOL1207789', 'SHP27-14079', ['SHPDN27-16971']),
    ('SOL1207554', 'SHP27-13846', ['SHPDN27-16257']),
    ('SOL1207295', 'SHP27-13584', ['SHPDN27-15924']),
    ('SOL1206984', 'SHP27-13275', ['SHPDN27-16060']),
    ('SOL1206872', 'SHP27-13165', ['SHPDN27-15711']),
    ('SOL1206392', 'SHP27-12693', []),  # blank item_code, no DN
]

def manual_clickpost(dn_name, so_name, is_ppcod=False, cod_amount=0):
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dn_data = r_dn.json().get('data', {})
    items_list = dn_data.get('items', [])
    grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
    posting_date = dn_data.get('posting_date', '')
    net_total = float(dn_data.get('net_total', 0) or 0)
    total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)
    addr_name = dn_data.get('shipping_address_name', '')

    r_addr = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    ad = r_addr.json().get('data', {}) if r_addr.status_code == 200 else {}
    drop_name = dn_data.get('customer_name', '')
    drop_phone = str(ad.get('phone', '') or '')
    drop_addr1 = str(ad.get('address_line1', '') or '')
    drop_addr2 = str(ad.get('address_line2', '') or '')
    drop_address = f'{drop_addr1}, {drop_addr2}'.strip(', ') if drop_addr2 else drop_addr1
    drop_city = str(ad.get('city', '') or '')
    drop_state = str(ad.get('state', '') or '')
    drop_pin = str(ad.get('pincode', '') or '')

    order_type = 'COD' if (is_ppcod and cod_amount > 0) else 'PREPAID'
    cod_val = cod_amount if is_ppcod else 0

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-22T10:00:00Z',
            },
            'drop_info': {
                'drop_name': drop_name, 'drop_phone': drop_phone, 'drop_address': drop_address,
                'drop_city': drop_city, 'drop_state': drop_state, 'drop_pincode': drop_pin,
                'drop_country': 'IN', 'drop_email': 'noreply@solara.in',
            },
            'shipment_details': {
                'order_type': order_type, 'invoice_value': grand_total, 'reference_number': so_name,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_val, 'courier_partner': cp_id,
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
        print(f'      Trying {cp_name}...')
        r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp = r_cp.json()
        meta = cp_resp.get('meta', {})
        if meta.get('success') and meta.get('status') == 200:
            awb = str(cp_resp.get('result', {}).get('waybill', ''))
            print(f'      SUCCESS! AWB={awb} via {cp_name}')
            upd = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
                json={'awb_number': awb, 'courier_partner': cp_name}, timeout=15)
            if upd.status_code != 200:
                print(f'      AWB save failed ({upd.status_code})')
            return awb, cp_name
        else:
            print(f'      FAIL {cp_name}: {meta.get("message","")[:200]}')
    return '', 'BOTH_FAILED'


for order_num, so_name, draft_dns in orders_to_process:
    print(f'\n{"="*50}')
    print(f'{order_num} | {so_name}')
    print(f'{"="*50}')

    is_ppcod = order_num in PPCOD_COD
    cod_amount = PPCOD_COD.get(order_num, 0)
    is_blank_sku = order_num in BLANK_SKU_FIX

    # Get Shopify order
    r_sh = requests.get(f'https://{STORE}/admin/api/2024-01/orders.json', headers=SH, params={
        'name': order_num, 'status': 'any', 'limit': 1,
    }, timeout=15)
    sh_orders = r_sh.json().get('orders', [])
    if not sh_orders:
        print(f'  Shopify NOT FOUND')
        results.append((order_num, so_name, '', '', 'SHOPIFY_NOT_FOUND'))
        continue
    shopify = sh_orders[0]
    sa = shopify.get('shipping_address', {}) or {}
    shopify_id = str(shopify.get('id', ''))

    # Get SO details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_data = r_so.json().get('data', {})
    cust_id = so_data.get('customer', '')
    cust_name = so_data.get('customer_name', '')
    old_addr = so_data.get('shipping_address_name', '')

    # Delete all draft DNs
    for dn in draft_dns:
        r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
        print(f'  Deleted draft {dn}: {r_del.status_code}')

    # Create/update address from Shopify
    name_str = f"{sa.get('first_name','')} {sa.get('last_name','')}".strip()
    pin = sa.get('zip', '')
    addr_name = f'{name_str} - {pin}-Shipping'
    addr_payload = {
        'address_title': name_str,
        'address_type': 'Shipping',
        'address_line1': sa.get('address1', '') or 'N/A',
        'address_line2': sa.get('address2', '') or '',
        'city': sa.get('city', '') or 'N/A',
        'state': sa.get('province', '') or '',
        'pincode': pin,
        'country': 'India',
        'phone': sa.get('phone', '') or '',
        'email_id': 'noreply@solara.in',
        'is_shipping_address': 1,
        'links': [{'link_doctype': 'Customer', 'link_name': cust_id}],
    }
    r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    if r_ae.status_code == 200:
        requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        print(f'  Address updated: {addr_name}')
    else:
        r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r_ac.status_code == 200:
            addr_name = r_ac.json().get('data', {}).get('name', addr_name)
            print(f'  Address created: {addr_name}')
        else:
            # Try alt name
            addr_payload['address_title'] = f'{name_str} - {pin}'
            r_ac2 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
            if r_ac2.status_code == 200:
                addr_name = r_ac2.json().get('data', {}).get('name', '')
                print(f'  Address created (alt): {addr_name}')
            else:
                print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')
                results.append((order_num, so_name, '', '', 'ADDR_FAIL'))
                continue

    # Update SO address
    requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={
        'shipping_address_name': addr_name, 'customer_address': addr_name,
    }, timeout=15)

    # Create DN
    if is_blank_sku:
        # Manual DN with correct items
        items_fix = BLANK_SKU_FIX[order_num]
        # Get SO item names for linking
        so_items = so_data.get('items', [])

        dn_items = []
        for i, item_fix in enumerate(items_fix):
            dn_item = {
                'item_code': item_fix['sku'],
                'qty': item_fix['qty'],
                'rate': float(item_fix['price']),
                'warehouse': 'Main Warehouse - WTBBPL',
                'against_sales_order': so_name,
            }
            # Link to SO item if available
            if i < len(so_items):
                dn_item['so_detail'] = so_items[i].get('name', '')
            dn_items.append(dn_item)

        dn_payload = {
            'customer': cust_id,
            'company': 'Win The Buy Box Private Limited',
            'shipping_address_name': addr_name,
            'customer_address': addr_name,
            'shopify_order_id': shopify_id,
            'shopify_order_number': order_num,
            'set_warehouse': 'Main Warehouse - WTBBPL',
            'items': dn_items,
        }
        r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    else:
        r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
            headers=H, params={'source_name': so_name}, timeout=15)
        if r_dn.status_code != 200:
            print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
            results.append((order_num, so_name, '', '', 'MAKE_DN_FAIL'))
            continue
        dn_draft = r_dn.json().get('message', {})
        dn_draft['shipping_address_name'] = addr_name
        dn_draft['customer_address'] = addr_name
        dn_draft['shopify_order_id'] = shopify_id
        dn_draft['shopify_order_number'] = order_num
        if is_ppcod and cod_amount > 0:
            dn_draft['custom_cod_amount'] = cod_amount

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
        results.append((order_num, so_name, '', '', 'DN_SAVE_FAIL'))
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
            results.append((order_num, so_name, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((order_num, so_name, dn_name, '', 'DN_SUBMIT_FAIL'))
        continue

    # Check AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''
    if awb:
        print(f'  AWB: {awb} via {courier}')
        results.append((order_num, so_name, dn_name, awb, courier))
    else:
        print(f'  No auto-AWB, trying manual Clickpost...')
        awb, courier = manual_clickpost(dn_name, so_name, is_ppcod, cod_amount)
        results.append((order_num, so_name, dn_name, awb, courier))


# SUMMARY
print('\n\n' + '='*70)
print('FINAL SUMMARY')
print('='*70)
ok = 0
fail = 0
for order_num, so, dn, awb, courier in results:
    status = 'OK' if awb else 'FAIL'
    if awb: ok += 1
    else: fail += 1
    print(f'{order_num:12s} | {so:15s} | {dn:20s} | {awb or "NO AWB":20s} | {courier}')
print(f'\n{ok} OK, {fail} FAILED out of {len(results)} processed')
