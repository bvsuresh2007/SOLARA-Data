import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'
COMPANY = 'Win The Buy Box Private Limited'

r_tok = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={
    'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password',
}, timeout=30)
SHOPIFY_TOKEN = r_tok.json().get('message', '')
STORE = 'dev-solara.myshopify.com'
SH = {'X-Shopify-Access-Token': SHOPIFY_TOKEN, 'Content-Type': 'application/json'}

results = []

def get_shopify_order(order_name):
    r = requests.get(f'https://{STORE}/admin/api/2024-01/orders.json', headers=SH, params={
        'name': order_name, 'status': 'any', 'limit': 1,
    }, timeout=15)
    return (r.json().get('orders', []) or [None])[0]

def create_or_get_customer(name_str):
    r = requests.get(f'{BASE}/api/resource/Customer', headers=H, params={
        'filters': json.dumps([['customer_name', '=', name_str]]),
        'fields': json.dumps(['name']),
        'limit_page_length': 1,
    }, timeout=15)
    custs = r.json().get('data', [])
    if custs:
        return custs[0]['name']
    # Create customer
    r2 = requests.post(f'{BASE}/api/resource/Customer', headers=H, json={
        'customer_name': name_str,
        'customer_type': 'Individual',
        'customer_group': 'Individual',
        'territory': 'India',
    }, timeout=15)
    if r2.status_code == 200:
        cid = r2.json().get('data', {}).get('name', '')
        print(f'    Customer created: {cid}')
        return cid
    else:
        print(f'    Customer create failed: {r2.status_code} {r2.text[:200]}')
        return None

def create_address(cust_id, sa, suffix=''):
    name_str = f"{sa.get('first_name','')} {sa.get('last_name','')}".strip()
    pin = sa.get('zip', '')
    addr_name = f'{name_str} - {pin}-Shipping{suffix}'
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
    r = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    if r.status_code == 200:
        r2 = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        if r2.status_code == 200:
            print(f'    Address updated: {addr_name}')
            return addr_name
        print(f'    Address update failed: {r2.status_code} {r2.text[:200]}')
        return addr_name
    else:
        r2 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r2.status_code == 200:
            an = r2.json().get('data', {}).get('name', addr_name)
            print(f'    Address created: {an}')
            return an
        # Try with -1 suffix if name collision
        if 'DuplicateEntryError' in r2.text or 'already exists' in r2.text.lower():
            addr_payload['address_title'] = f'{name_str} - {pin}'
            r3 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
            if r3.status_code == 200:
                an = r3.json().get('data', {}).get('name', '')
                print(f'    Address created (alt): {an}')
                return an
        print(f'    Address create failed: {r2.status_code} {r2.text[:200]}')
        return None

def manual_clickpost(dn_name, so_name, ref_suffix=''):
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

    ref = f'{so_name}{ref_suffix}'
    order_type = 'PREPAID'
    cod_value = 0
    cot = str(dn_data.get('custom_order_type', '') or '')
    if 'cod' in cot.lower() or 'ppcod' in cot.lower():
        cod_value = float(dn_data.get('custom_cod_amount', 0) or 0)
        if cod_value > 0:
            order_type = 'COD'

    for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
        cp_payload = {
            'pickup_info': {
                'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-22T10:00:00Z',
            },
            'drop_info': {
                'drop_name': drop_name, 'drop_phone': drop_phone,
                'drop_address': drop_address,
                'drop_city': drop_city, 'drop_state': drop_state, 'drop_pincode': drop_pin,
                'drop_country': 'IN', 'drop_email': 'noreply@solara.in',
            },
            'shipment_details': {
                'order_type': order_type, 'invoice_value': grand_total, 'reference_number': ref,
                'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                           'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                'delivery_type': 'FORWARD', 'cod_value': cod_value, 'courier_partner': cp_id,
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
                print(f'      AWB save to DN failed ({upd.status_code}), will need manual update')
            return awb, cp_name
        else:
            print(f'      FAIL {cp_name}: {meta.get("message","")[:200]}')
    return '', 'BOTH_FAILED'


# ========== PART 0: Save AWB for SOL1209674 ==========
print('='*60)
print('PART 0: Save AWB for SOL1209674')
print('='*60)
upd = requests.put(f'{BASE}/api/resource/Delivery Note/SHPDN27-18960', headers=H,
    json={'awb_number': '29044411258040', 'courier_partner': 'Delhivery'}, timeout=15)
print(f'  Save AWB: {upd.status_code}')
if upd.status_code != 200:
    print(f'  {upd.text[:200]}')
results.append(('SOL1209674', 'SHP27-15933', 'SHPDN27-18960', '29044411258040', 'Delhivery'))

# ========== PART 1: Fix 3 draft DNs - delete + recreate with correct address ==========
print('\n' + '='*60)
print('PART 1: Fix 3 draft DNs (address mismatch)')
print('='*60)

draft_fix = [
    ('SOL1209492', 'SHP27-15751', 'SHPDN27-18889', 'Anil Kumar M'),
    ('SOL1209466', 'SHP27-15726', 'SHPDN27-18909', 'Pradeep . - 2'),
    ('SOL1209406', 'SHP27-15669', 'SHPDN27-18946', 'Fathima Nasmin'),
]

for order_num, so_name, dn_name, cust_id in draft_fix:
    print(f'\n--- {order_num} ({so_name}) ---')
    shopify = get_shopify_order(order_num)
    if not shopify:
        print(f'    Shopify order not found!')
        results.append((order_num, so_name, '', '', 'SHOPIFY_NOT_FOUND'))
        continue
    sa = shopify.get('shipping_address', {}) or {}
    shopify_id = str(shopify.get('id', ''))

    # Delete draft DN
    r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    print(f'    Deleted draft DN {dn_name}: {r_del.status_code}')

    # Create correct address from Shopify
    addr_name = create_address(cust_id, sa)
    if not addr_name:
        results.append((order_num, so_name, '', '', 'ADDR_FAIL'))
        continue

    # Update SO address
    r_so_upd = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={
        'shipping_address_name': addr_name, 'customer_address': addr_name,
    }, timeout=15)
    print(f'    SO address updated: {r_so_upd.status_code}')

    # Create new DN
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'    make_delivery_note failed: {r_dn.status_code}')
        results.append((order_num, so_name, '', '', 'MAKE_DN_FAIL'))
        continue
    dn_draft = r_dn.json().get('message', {})
    dn_draft['shipping_address_name'] = addr_name
    dn_draft['customer_address'] = addr_name
    dn_draft['shopify_order_id'] = shopify_id
    dn_draft['shopify_order_number'] = order_num

    for tax in dn_draft.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    r3 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r3.status_code != 200:
        print(f'    DN save failed: {r3.status_code} {r3.text[:300]}')
        results.append((order_num, so_name, '', '', 'DN_SAVE_FAIL'))
        continue
    new_dn = r3.json().get('data', {}).get('name', '')
    print(f'    DN created: {new_dn}')

    # Submit
    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'    DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'    DN submitted (417 OK)!')
        else:
            print(f'    DN submit failed: {r4.text[:300]}')
            results.append((order_num, so_name, new_dn, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'    DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((order_num, so_name, new_dn, '', 'DN_SUBMIT_FAIL'))
        continue

    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''
    if awb:
        print(f'    AWB: {awb} via {courier}')
        results.append((order_num, so_name, new_dn, awb, courier))
    else:
        print(f'    No auto-AWB, trying manual...')
        awb, courier = manual_clickpost(new_dn, so_name)
        results.append((order_num, so_name, new_dn, awb, courier))


# ========== PART 2: SOL1209443 — fix item_code + create DN ==========
print('\n' + '='*60)
print('PART 2: SOL1209443 — create DN manually')
print('='*60)

print('\n--- SOL1209443 (SHP27-15703) ---')
shopify443 = get_shopify_order('SOL1209443')
sa443 = shopify443.get('shipping_address', {}) if shopify443 else {}
shopify_id_443 = str(shopify443.get('id', '')) if shopify443 else ''

# Get SO details
r_so443 = requests.get(f'{BASE}/api/resource/Sales Order/SHP27-15703', headers=H, timeout=15)
so443 = r_so443.json().get('data', {})
addr443 = so443.get('shipping_address_name', '')
cust443 = so443.get('customer', '')

# Create DN manually (since make_delivery_note fails with blank item)
dn443_payload = {
    'customer': cust443,
    'company': COMPANY,
    'shipping_address_name': addr443,
    'customer_address': addr443,
    'shopify_order_id': shopify_id_443,
    'shopify_order_number': 'SOL1209443',
    'set_warehouse': 'Main Warehouse - WTBBPL',
    'items': [{
        'item_code': 'SOL-INS-WB-208R',
        'qty': 1,
        'rate': 569.05,
        'against_sales_order': 'SHP27-15703',
        'warehouse': 'Main Warehouse - WTBBPL',
    }],
}
r_dn443 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn443_payload, timeout=30)
if r_dn443.status_code == 200:
    dn443_name = r_dn443.json().get('data', {}).get('name', '')
    print(f'    DN created: {dn443_name}')

    r_sub443 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn443_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub443.status_code == 200:
        print(f'    DN submitted!')
    elif r_sub443.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn443_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'    DN submitted (417 OK)!')
        else:
            print(f'    DN submit failed: {r_sub443.text[:300]}')
            results.append(('SOL1209443', 'SHP27-15703', dn443_name, '', 'DN_SUBMIT_FAIL'))
    else:
        print(f'    DN submit failed: {r_sub443.status_code} {r_sub443.text[:300]}')
        results.append(('SOL1209443', 'SHP27-15703', dn443_name, '', 'DN_SUBMIT_FAIL'))

    if ('SOL1209443', 'SHP27-15703', dn443_name, '', 'DN_SUBMIT_FAIL') not in results:
        time.sleep(3)
        r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn443_name}', headers=H, params={
            'fields': json.dumps(['awb_number', 'courier_partner'])
        }, timeout=15)
        d = r6.json().get('data', {})
        awb = d.get('awb_number', '') or ''
        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'    AWB: {awb} via {courier}')
            results.append(('SOL1209443', 'SHP27-15703', dn443_name, awb, courier))
        else:
            awb, courier = manual_clickpost(dn443_name, 'SHP27-15703')
            results.append(('SOL1209443', 'SHP27-15703', dn443_name, awb, courier))
else:
    print(f'    DN save failed: {r_dn443.status_code} {r_dn443.text[:300]}')
    results.append(('SOL1209443', 'SHP27-15703', '', '', 'DN_SAVE_FAIL'))


# ========== PART 3: 6 missing SOs ==========
print('\n' + '='*60)
print('PART 3: 6 missing SOs → create Customer + Address + SO + DN + AWB')
print('='*60)

missing_orders = [
    ('SOL1209684', 'Shashi Gupta', [{'sku': 'SOL-AF-501', 'qty': 1, 'price': 7799}], 'Prepaid', 0),
    ('SOL1209494', 'Sharada Potluri', [{'sku': 'SOL-JUC-121', 'qty': 1, 'price': 7499}], 'Prepaid', 0),
    ('SOL1209425', 'Radhe Enterprises', [
        {'sku': 'SOL-AF-501-CVR-BAG', 'qty': 1, 'price': 499},
        {'sku': 'SOL-AF-501-SIL-BASKET-P6-SPY-101', 'qty': 1, 'price': 8199},
        {'sku': 'SOL-GIFWRAP', 'qty': 1, 'price': 199},
    ], 'Prepaid', 0),
    ('SOL1209410', 'Harshini gandhi', [{'sku': 'SOL-AF-501', 'qty': 1, 'price': 7799}], 'Prepaid', 0),
    ('SOL1209624', 'Ravindren S S', [{'sku': 'SOL-JUC-121', 'qty': 1, 'price': 7499}], 'PPCOD', 7499),
    ('SOL1209469', 'Alok Pradhan', [{'sku': 'SOL-JUC-121-GLSTUM-101', 'qty': 1, 'price': 7699}], 'PPCOD', 7699),
]

for order_num, cust_name, items, order_type, cod_amount in missing_orders:
    print(f'\n--- {order_num} ({cust_name}) ---')
    shopify = get_shopify_order(order_num)
    if not shopify:
        print(f'    Shopify not found!')
        results.append((order_num, '', '', '', 'SHOPIFY_NOT_FOUND'))
        continue
    sa = shopify.get('shipping_address', {}) or {}
    shopify_id = str(shopify.get('id', ''))

    # Create/get customer
    cust_id = create_or_get_customer(cust_name)
    if not cust_id:
        results.append((order_num, '', '', '', 'CUST_FAIL'))
        continue

    # Create address
    addr_name = create_address(cust_id, sa)
    if not addr_name:
        results.append((order_num, '', '', '', 'ADDR_FAIL'))
        continue

    # Create SO without shopify_order_id (bypass hook)
    so_items = [{'item_code': it['sku'], 'qty': it['qty'], 'rate': float(it['price']),
                 'delivery_date': '2026-05-25', 'warehouse': 'Main Warehouse - WTBBPL'} for it in items]
    so_payload = {
        'customer': cust_id,
        'transaction_date': '2026-05-22',
        'delivery_date': '2026-05-25',
        'company': COMPANY,
        'order_type': 'Sales',
        'currency': 'INR',
        'selling_price_list': 'Standard Selling',
        'customer_address': addr_name,
        'shipping_address_name': addr_name,
        'custom_order_type': order_type,
        'items': so_items,
    }
    if cod_amount > 0:
        so_payload['custom_cod_amount'] = cod_amount

    r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
    if r_so.status_code != 200:
        print(f'    SO create failed: {r_so.status_code} {r_so.text[:300]}')
        results.append((order_num, '', '', '', 'SO_CREATE_FAIL'))
        continue
    so_name = r_so.json().get('data', {}).get('name', '')
    print(f'    SO created: {so_name}')

    r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code != 200:
        print(f'    SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
        results.append((order_num, so_name, '', '', 'SO_SUBMIT_FAIL'))
        continue
    print(f'    SO submitted!')

    # Create DN
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'    make_delivery_note failed: {r_dn.status_code}')
        results.append((order_num, so_name, '', '', 'MAKE_DN_FAIL'))
        continue
    dn_draft = r_dn.json().get('message', {})
    dn_draft['shipping_address_name'] = addr_name
    dn_draft['customer_address'] = addr_name
    dn_draft['shopify_order_id'] = shopify_id
    dn_draft['shopify_order_number'] = order_num
    if order_type == 'PPCOD' and cod_amount > 0:
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
        print(f'    DN save failed: {r3.status_code} {r3.text[:300]}')
        results.append((order_num, so_name, '', '', 'DN_SAVE_FAIL'))
        continue
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'    DN created: {dn_name}')

    r4 = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r4.status_code == 200:
        print(f'    DN submitted!')
    elif r4.status_code == 417:
        time.sleep(2)
        r5 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r5.json().get('data', {}).get('docstatus') == 1:
            print(f'    DN submitted (417 OK)!')
        else:
            print(f'    DN submit failed: {r4.text[:300]}')
            results.append((order_num, so_name, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue
    else:
        print(f'    DN submit failed: {r4.status_code} {r4.text[:300]}')
        results.append((order_num, so_name, dn_name, '', 'DN_SUBMIT_FAIL'))
        continue

    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''
    if awb:
        print(f'    AWB: {awb} via {courier}')
        results.append((order_num, so_name, dn_name, awb, courier))
    else:
        print(f'    No auto-AWB, trying manual...')
        awb, courier = manual_clickpost(dn_name, so_name)
        results.append((order_num, so_name, dn_name, awb, courier))


# ========== SUMMARY ==========
print('\n\n' + '='*60)
print('FINAL SUMMARY')
print('='*60)
for order_num, so, dn, awb, courier in results:
    print(f'{order_num:12s} | {so:20s} | {dn:20s} | {awb or "NO AWB":20s} | {courier}')
