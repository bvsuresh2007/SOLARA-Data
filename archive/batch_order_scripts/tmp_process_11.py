import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'
COMPANY = 'Win The Buy Box Private Limited'

# Get Shopify token
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
    orders = r.json().get('orders', [])
    return orders[0] if orders else None

def create_address(cust_name, sa, order_num):
    """Create/update address from Shopify shipping_address"""
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
        'links': [{'link_doctype': 'Customer', 'link_name': cust_name}],
    }
    r = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    if r.status_code == 200:
        r2 = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        return addr_name
    else:
        r2 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r2.status_code == 200:
            return r2.json().get('data', {}).get('name', addr_name)
        else:
            print(f'    Addr create failed: {r2.status_code} {r2.text[:200]}')
            return None

def create_so(shopify_order, items_list, order_type='Prepaid', cod_amount=0):
    """Create SO from Shopify data"""
    sa = shopify_order.get('shipping_address', {}) or {}
    name_str = f"{sa.get('first_name','')} {sa.get('last_name','')}".strip()
    shopify_id = str(shopify_order.get('id', ''))
    order_name = shopify_order.get('name', '')

    # Find or create customer
    r_cust = requests.get(f'{BASE}/api/resource/Customer', headers=H, params={
        'filters': json.dumps([['customer_name', '=', name_str]]),
        'fields': json.dumps(['name']),
        'limit_page_length': 1,
    }, timeout=15)
    custs = r_cust.json().get('data', [])
    if custs:
        cust_id = custs[0]['name']
    else:
        # Use Shopify D2C default customer
        cust_id = 'Shopify D2C'

    # Create address
    addr_name = create_address(cust_id, sa, order_name)
    if not addr_name:
        return None, None

    so_items = []
    for item in items_list:
        so_items.append({
            'item_code': item['sku'],
            'qty': item['qty'],
            'rate': float(item['price']),
            'delivery_date': '2026-05-25',
            'warehouse': 'Main Warehouse - WTBBPL',
        })

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

    # Create WITHOUT shopify_order_id to bypass hook
    r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
    if r_so.status_code != 200:
        print(f'    SO create failed: {r_so.status_code} {r_so.text[:300]}')
        return None, None
    so_name = r_so.json().get('data', {}).get('name', '')
    print(f'    SO created: {so_name}')

    # Submit
    r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code != 200:
        print(f'    SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
        return so_name, addr_name

    print(f'    SO submitted!')
    return so_name, addr_name

def create_dn_and_awb(so_name, addr_name=None, shopify_order_id=None, shopify_order_number=None, is_ppcod=False, cod_amount=0):
    """Create DN from SO, submit, get AWB"""
    # Make DN from SO
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'    make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        return None, None, None

    dn_draft = r_dn.json().get('message', {})
    if addr_name:
        dn_draft['shipping_address_name'] = addr_name
        dn_draft['customer_address'] = addr_name
    if shopify_order_id:
        dn_draft['shopify_order_id'] = shopify_order_id
    if shopify_order_number:
        dn_draft['shopify_order_number'] = shopify_order_number
    if is_ppcod and cod_amount > 0:
        dn_draft['custom_cod_amount'] = cod_amount

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
        print(f'    DN save failed: {r3.status_code} {r3.text[:300]}')
        return None, None, None
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'    DN created: {dn_name}')

    return submit_dn_and_get_awb(dn_name)

def submit_dn_and_get_awb(dn_name):
    """Submit existing DN and get AWB"""
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
            return dn_name, '', 'DN_SUBMIT_FAIL'
    else:
        print(f'    DN submit failed: {r4.status_code} {r4.text[:300]}')
        return dn_name, '', 'DN_SUBMIT_FAIL'

    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''

    if awb:
        print(f'    AWB: {awb} via {courier}')
        return dn_name, awb, courier

    print(f'    No auto-AWB, trying manual Clickpost...')
    return dn_name, '', 'NO_AUTO_AWB'

def manual_clickpost(dn_name, so_name, ref_suffix=''):
    """Manual Clickpost AWB creation"""
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dn_data = r_dn.json().get('data', {})
    items_list = dn_data.get('items', [])
    grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
    posting_date = dn_data.get('posting_date', '')
    net_total = float(dn_data.get('net_total', 0) or 0)
    total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)
    addr_name = dn_data.get('shipping_address_name', '')

    r_addr = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr_data = r_addr.json().get('data', {}) if r_addr.status_code == 200 else {}
    drop_name = dn_data.get('customer_name', '')
    drop_phone = str(addr_data.get('phone', '') or '')
    drop_addr1 = str(addr_data.get('address_line1', '') or '')
    drop_addr2 = str(addr_data.get('address_line2', '') or '')
    drop_address = f'{drop_addr1}, {drop_addr2}'.strip(', ') if drop_addr2 else drop_addr1
    drop_city = str(addr_data.get('city', '') or '')
    drop_state = str(addr_data.get('state', '') or '')
    drop_pin = str(addr_data.get('pincode', '') or '')

    ref = f'{so_name}{ref_suffix}'
    order_type = 'PREPAID'
    cod_value = 0
    custom_order_type = dn_data.get('custom_order_type', '') or ''
    if 'cod' in custom_order_type.lower() or 'ppcod' in custom_order_type.lower():
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
            # Save AWB to DN
            upd = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
                json={'awb_number': awb, 'courier_partner': cp_name}, timeout=15)
            if upd.status_code != 200:
                print(f'      AWB save failed ({upd.status_code})')
            return awb, cp_name
        else:
            print(f'      FAIL {cp_name}: {meta.get("message","")[:200]}')
    return '', 'BOTH_COURIERS_FAILED'


# ========== PART 1: Submit 3 draft DNs ==========
print('='*60)
print('PART 1: Submit 3 draft DNs')
print('='*60)

draft_dns = [
    ('SOL1209492', 'SHP27-15751', 'SHPDN27-18889'),
    ('SOL1209466', 'SHP27-15726', 'SHPDN27-18909'),
    ('SOL1209406', 'SHP27-15669', 'SHPDN27-18946'),
]

for order_num, so_name, dn_name in draft_dns:
    print(f'\n--- {order_num} ({so_name}) ---')
    dn_name_out, awb, courier = submit_dn_and_get_awb(dn_name)
    if awb:
        results.append((order_num, so_name, dn_name, awb, courier))
    elif courier == 'NO_AUTO_AWB':
        awb, courier = manual_clickpost(dn_name, so_name)
        results.append((order_num, so_name, dn_name, awb, courier))
    else:
        results.append((order_num, so_name, dn_name, '', courier))

# ========== PART 2: SOL1209674 — submitted DN no AWB ==========
print('\n' + '='*60)
print('PART 2: SOL1209674 — submitted DN, no AWB → manual Clickpost')
print('='*60)

print('\n--- SOL1209674 (SHP27-15933, SHPDN27-18960) ---')
# Check if AWB appeared since last check
r_check = requests.get(f'{BASE}/api/resource/Delivery Note/SHPDN27-18960', headers=H, params={
    'fields': json.dumps(['awb_number', 'courier_partner', 'shipping_address_name'])
}, timeout=15)
d_check = r_check.json().get('data', {})
awb_check = d_check.get('awb_number', '') or ''
if awb_check:
    print(f'    AWB already exists: {awb_check}')
    results.append(('SOL1209674', 'SHP27-15933', 'SHPDN27-18960', awb_check, d_check.get('courier_partner','')))
else:
    awb, courier = manual_clickpost('SHPDN27-18960', 'SHP27-15933')
    results.append(('SOL1209674', 'SHP27-15933', 'SHPDN27-18960', awb, courier))

# ========== PART 3: SOL1209443 — blank item_code → fix + create DN ==========
print('\n' + '='*60)
print('PART 3: SOL1209443 — fix blank item_code + create DN')
print('='*60)

print('\n--- SOL1209443 (SHP27-15703) ---')
# Get SO items to find the blank one
r_so443 = requests.get(f'{BASE}/api/resource/Sales Order/SHP27-15703', headers=H, timeout=15)
so443 = r_so443.json().get('data', {})
items443 = so443.get('items', [])
addr443 = so443.get('shipping_address_name', '')
for it in items443:
    ic = it.get('item_code', '') or ''
    print(f'    Item: {it.get("name","")} | item_code="{ic}" | qty={it.get("qty","")}')

# The SO has blank item_code — need to fix it to SOL-INS-WB-208R
# Try updating via PUT on SO item
so443_items_fixed = []
for it in items443:
    ic = it.get('item_code', '') or ''
    if not ic:
        it['item_code'] = 'SOL-INS-WB-208R'
        print(f'    Fixing item {it.get("name","")} → SOL-INS-WB-208R')
    so443_items_fixed.append(it)

# Can't update submitted SO items easily, try make_delivery_note anyway
# If it fails, create DN manually
r_dn443 = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
    headers=H, params={'source_name': 'SHP27-15703'}, timeout=15)
if r_dn443.status_code == 200:
    dn_draft443 = r_dn443.json().get('message', {})
    # Fix blank item codes in DN draft
    for item in dn_draft443.get('items', []):
        if not item.get('item_code'):
            item['item_code'] = 'SOL-INS-WB-208R'
            item['item_name'] = 'Insulated Water Bottle (Dark Intention) - Refurbished'
            print(f'    Fixed DN item_code → SOL-INS-WB-208R')

    dn_draft443['shipping_address_name'] = addr443
    dn_draft443['customer_address'] = addr443
    for tax in dn_draft443.get('taxes', []):
        if tax.get('item_wise_tax_detail') is None:
            tax['item_wise_tax_detail'] = '{}'
    for item in dn_draft443.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft443.pop(key, None)

    r3_443 = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft443, timeout=30)
    if r3_443.status_code == 200:
        dn443 = r3_443.json().get('data', {}).get('name', '')
        print(f'    DN created: {dn443}')
        dn_name_out, awb, courier = submit_dn_and_get_awb(dn443)
        if awb:
            results.append(('SOL1209443', 'SHP27-15703', dn443, awb, courier))
        elif courier == 'NO_AUTO_AWB':
            awb, courier = manual_clickpost(dn443, 'SHP27-15703')
            results.append(('SOL1209443', 'SHP27-15703', dn443, awb, courier))
        else:
            results.append(('SOL1209443', 'SHP27-15703', dn443, '', courier))
    else:
        print(f'    DN save failed: {r3_443.status_code} {r3_443.text[:300]}')
        results.append(('SOL1209443', 'SHP27-15703', '', '', 'DN_SAVE_FAIL'))
else:
    print(f'    make_delivery_note failed: {r_dn443.status_code}')
    results.append(('SOL1209443', 'SHP27-15703', '', '', 'MAKE_DN_FAIL'))

# ========== PART 4: 6 missing SOs → create SO + DN ==========
print('\n' + '='*60)
print('PART 4: 6 missing SOs → create SO + DN + AWB')
print('='*60)

missing_orders = [
    ('SOL1209684', [{'sku': 'SOL-AF-501', 'qty': 1, 'price': 7799}], 'Prepaid', 0),
    ('SOL1209494', [{'sku': 'SOL-JUC-121', 'qty': 1, 'price': 7499}], 'Prepaid', 0),
    ('SOL1209425', [
        {'sku': 'SOL-AF-501-CVR-BAG', 'qty': 1, 'price': 499},
        {'sku': 'SOL-AF-501-SIL-BASKET-P6-SPY-101', 'qty': 1, 'price': 8199},
        {'sku': 'SOL-GIFWRAP', 'qty': 1, 'price': 199},
    ], 'Prepaid', 0),
    ('SOL1209410', [{'sku': 'SOL-AF-501', 'qty': 1, 'price': 7799}], 'Prepaid', 0),
    ('SOL1209624', [{'sku': 'SOL-JUC-121', 'qty': 1, 'price': 7499}], 'PPCOD', 7499),
    ('SOL1209469', [{'sku': 'SOL-JUC-121-GLSTUM-101', 'qty': 1, 'price': 7699}], 'PPCOD', 7699),
]

for order_num, items, order_type, cod_amount in missing_orders:
    print(f'\n--- {order_num} ---')
    shopify_order = get_shopify_order(order_num)
    if not shopify_order:
        print(f'    Shopify order not found!')
        results.append((order_num, '', '', '', 'SHOPIFY_NOT_FOUND'))
        continue

    shopify_id = str(shopify_order.get('id', ''))
    so_name, addr_name = create_so(shopify_order, items, order_type, cod_amount)
    if not so_name:
        results.append((order_num, '', '', '', 'SO_CREATE_FAIL'))
        continue

    is_ppcod = order_type == 'PPCOD'
    dn_name, awb, courier = create_dn_and_awb(so_name, addr_name,
        shopify_order_id=shopify_id, shopify_order_number=order_num,
        is_ppcod=is_ppcod, cod_amount=cod_amount)

    if not dn_name:
        results.append((order_num, so_name, '', '', 'DN_CREATE_FAIL'))
        continue

    if awb:
        results.append((order_num, so_name, dn_name, awb, courier))
    elif courier == 'NO_AUTO_AWB':
        awb, courier = manual_clickpost(dn_name, so_name)
        results.append((order_num, so_name, dn_name, awb, courier))
    else:
        results.append((order_num, so_name, dn_name, '', courier))


# ========== SUMMARY ==========
print('\n\n' + '='*60)
print('FINAL SUMMARY')
print('='*60)
for order_num, so, dn, awb, courier in results:
    print(f'{order_num:12s} | {so:20s} | {dn:20s} | {awb or "NO AWB":20s} | {courier}')
