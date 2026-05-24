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

# PPCOD
PPCOD_COD = {'SOL1209818': 7299.0}

# Orders with existing SO + draft DN
existing_so_draft_dn = {
    'SOL1209695': ('SHP27-15953', ['SHPDN27-19289']),
    'SOL1209706': ('SHP27-15964', ['SHPDN27-19281']),
    'SOL1209722': ('SHP27-15979', ['SHPDN27-19271']),
    'SOL1209765': ('SHP27-16022', ['SHPDN27-19236']),
    'SOL1209866': ('SHP27-16126', ['SHPDN27-19172']),
    'SOL1209871': ('SHP27-16131', ['SHPDN27-19170']),
}

# Orders with existing SO, no DN
existing_so_no_dn = {
    'SOL1209739': 'SHP27-15996',
    'SOL1209843': 'SHP27-16103',
    'SOL1209978': 'SHP27-16233',
}

# Orders with existing SO, submitted DN but no AWB
existing_so_submitted_dn = {
    'SOL1209789': ('SHP27-16046', 'SHPDN27-19217'),
    'SOL1209818': ('SHP27-16081', 'SHPDN27-19325'),
}

# Orders with NO SO
no_so = {
    'SOL1209834': [
        {'sku': 'SOL-AF-501-SIL-BASKET-P6-SPY-101', 'qty': 1, 'price': 8199},
        {'sku': 'SOL-CI-PNY-101', 'qty': 1, 'price': 1099},
        {'sku': 'SOL-CI-KD-103-DT-102-FP-102', 'qty': 1, 'price': 2999},
        {'sku': 'SOL-CKW-WSPA-101', 'qty': 1, 'price': 299},
    ],
    'SOL1209894': [
        {'sku': 'SOL-INS-WB-305', 'qty': 1, 'price': 1999},
        {'sku': 'SOL-INS-WB-301', 'qty': 1, 'price': 1999},
    ],
    'SOL1209976': [
        {'sku': 'SOL-AF-PP-101', 'qty': 1, 'price': 299},
        {'sku': 'SOL-AF-SIL-BASKET-P6-SPY-101-AF-PP-101', 'qty': 1, 'price': 799},
        {'sku': 'SOL-JUC-BAG-121', 'qty': 1, 'price': 499},
        {'sku': 'SOL-AFO-501-JUC-121', 'qty': 1, 'price': 12999},
        {'sku': 'SOL-AF-501-CVR-BAG', 'qty': 1, 'price': 499},
    ],
}

ALL_ORDERS = ['SOL1209695','SOL1209706','SOL1209722','SOL1209739','SOL1209765',
              'SOL1209789','SOL1209818','SOL1209834','SOL1209843','SOL1209866',
              'SOL1209871','SOL1209894','SOL1209976','SOL1209978']

def get_shopify(order_name):
    r = requests.get(f'https://{STORE}/admin/api/2024-01/orders.json', headers=SH, params={
        'name': order_name, 'status': 'any', 'limit': 1,
    }, timeout=15)
    orders = r.json().get('orders', [])
    return orders[0] if orders else None

def create_or_get_customer(name_str):
    r = requests.get(f'{BASE}/api/resource/Customer', headers=H, params={
        'filters': json.dumps([['customer_name', '=', name_str]]),
        'fields': json.dumps(['name']), 'limit_page_length': 1,
    }, timeout=15)
    custs = r.json().get('data', [])
    if custs:
        return custs[0]['name']
    r2 = requests.post(f'{BASE}/api/resource/Customer', headers=H, json={
        'customer_name': name_str, 'customer_type': 'Individual',
        'customer_group': 'Individual', 'territory': 'India',
    }, timeout=15)
    if r2.status_code == 200:
        cid = r2.json().get('data', {}).get('name', '')
        print(f'    Customer created: {cid}')
        return cid
    print(f'    Customer create failed: {r2.status_code} {r2.text[:200]}')
    return None

def create_address(cust_id, sa):
    name_str = f"{sa.get('first_name','')} {sa.get('last_name','')}".strip()
    pin = sa.get('zip', '')
    addr_name = f'{name_str} - {pin}-Shipping'
    addr_payload = {
        'address_title': name_str, 'address_type': 'Shipping',
        'address_line1': sa.get('address1', '') or 'N/A',
        'address_line2': sa.get('address2', '') or '',
        'city': sa.get('city', '') or 'N/A', 'state': sa.get('province', '') or '',
        'pincode': pin, 'country': 'India',
        'phone': sa.get('phone', '') or '', 'email_id': 'noreply@solara.in',
        'is_shipping_address': 1,
        'links': [{'link_doctype': 'Customer', 'link_name': cust_id}],
    }
    r = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    if r.status_code == 200:
        requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        return addr_name
    r2 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r2.status_code == 200:
        return r2.json().get('data', {}).get('name', addr_name)
    addr_payload['address_title'] = f'{name_str} - {pin}'
    r3 = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r3.status_code == 200:
        return r3.json().get('data', {}).get('name', '')
    print(f'    Addr fail: {r2.status_code} {r2.text[:150]}')
    return None

def manual_clickpost(dn_name, so_name, is_ppcod=False, cod_amount=0):
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
    dd = r_dn.json().get('data', {})
    items_list = dd.get('items', [])
    grand_total = max(float(dd.get('grand_total', 0) or 0), 1.0)
    posting_date = dd.get('posting_date', '')
    net_total = float(dd.get('net_total', 0) or 0)
    total_taxes = float(dd.get('total_taxes_and_charges', 0) or 0)
    addr_name = dd.get('shipping_address_name', '')

    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    ad = r_a.json().get('data', {}) if r_a.status_code == 200 else {}
    drop_name = dd.get('customer_name', '')
    drop_phone = str(ad.get('phone', '') or '')
    a1 = str(ad.get('address_line1', '') or '')
    a2 = str(ad.get('address_line2', '') or '')
    drop_address = f'{a1}, {a2}'.strip(', ') if a2 else a1
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
                'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-23T10:00:00Z',
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
                print(f'      AWB save to DN failed ({upd.status_code})')
            return awb, cp_name
        else:
            print(f'      FAIL {cp_name}: {meta.get("message","")[:200]}')
    return '', 'BOTH_FAILED'

def process_order_with_so(order_num, so_name, draft_dns, shopify, is_ppcod=False, cod_amount=0):
    """Process an order that already has a SO"""
    sa = shopify.get('shipping_address', {}) or {}
    shopify_id = str(shopify.get('id', ''))

    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_data = r_so.json().get('data', {})
    cust_id = so_data.get('customer', '')

    # Delete draft DNs
    for dn in draft_dns:
        r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=15)
        print(f'  Deleted draft {dn}: {r_del.status_code}')

    # Create/update address
    addr_name = create_address(cust_id, sa)
    if not addr_name:
        return '', '', 'ADDR_FAIL'

    # Update SO address
    requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={
        'shipping_address_name': addr_name, 'customer_address': addr_name,
    }, timeout=15)

    # Create DN
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        return '', '', 'MAKE_DN_FAIL'
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
        return '', '', 'DN_SAVE_FAIL'
    dn_name = r3.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

    # Submit
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
            return dn_name, '', 'DN_SUBMIT_FAIL'
    else:
        print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
        return dn_name, '', 'DN_SUBMIT_FAIL'

    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '') or ''
    courier = d.get('courier_partner', '') or ''
    if awb:
        print(f'  AWB: {awb} via {courier}')
        return dn_name, awb, courier
    print(f'  No auto-AWB, trying manual...')
    awb, courier = manual_clickpost(dn_name, so_name, is_ppcod, cod_amount)
    return dn_name, awb, courier


for order_num in ALL_ORDERS:
    print(f'\n{"="*55}')
    print(f'{order_num}')
    print(f'{"="*55}')

    is_ppcod = order_num in PPCOD_COD
    cod_amount = PPCOD_COD.get(order_num, 0)

    shopify = get_shopify(order_num)
    if not shopify:
        print(f'  Shopify NOT FOUND')
        results.append((order_num, '', '', '', 'SHOPIFY_NOT_FOUND'))
        continue

    sa = shopify.get('shipping_address', {}) or {}
    shopify_id = str(shopify.get('id', ''))

    # Case 1: Submitted DN, no AWB → manual Clickpost only
    if order_num in existing_so_submitted_dn:
        so_name, dn_name = existing_so_submitted_dn[order_num]
        print(f'  Submitted DN {dn_name}, trying manual Clickpost...')
        awb, courier = manual_clickpost(dn_name, so_name, is_ppcod, cod_amount)
        results.append((order_num, so_name, dn_name, awb, courier))
        continue

    # Case 2: Existing SO + draft DN → delete draft, fix address, recreate
    if order_num in existing_so_draft_dn:
        so_name, draft_dns = existing_so_draft_dn[order_num]
        dn_name, awb, courier = process_order_with_so(order_num, so_name, draft_dns, shopify, is_ppcod, cod_amount)
        results.append((order_num, so_name, dn_name, awb, courier))
        continue

    # Case 3: Existing SO, no DN
    if order_num in existing_so_no_dn:
        so_name = existing_so_no_dn[order_num]
        dn_name, awb, courier = process_order_with_so(order_num, so_name, [], shopify, is_ppcod, cod_amount)
        results.append((order_num, so_name, dn_name, awb, courier))
        continue

    # Case 4: No SO → create customer, address, SO, DN
    if order_num in no_so:
        items = no_so[order_num]
        name_str = f"{sa.get('first_name','')} {sa.get('last_name','')}".strip()
        cust_id = create_or_get_customer(name_str)
        if not cust_id:
            results.append((order_num, '', '', '', 'CUST_FAIL'))
            continue

        addr_name = create_address(cust_id, sa)
        if not addr_name:
            results.append((order_num, '', '', '', 'ADDR_FAIL'))
            continue

        so_items = [{'item_code': it['sku'], 'qty': it['qty'], 'rate': float(it['price']),
                     'delivery_date': '2026-05-25', 'warehouse': 'Main Warehouse - WTBBPL'} for it in items]
        so_payload = {
            'customer': cust_id, 'transaction_date': '2026-05-23',
            'delivery_date': '2026-05-25', 'company': COMPANY,
            'order_type': 'Sales', 'currency': 'INR',
            'selling_price_list': 'Standard Selling',
            'customer_address': addr_name, 'shipping_address_name': addr_name,
            'custom_order_type': 'Prepaid', 'items': so_items,
        }
        r_so = requests.post(f'{BASE}/api/resource/Sales Order', headers=H, json=so_payload, timeout=30)
        if r_so.status_code != 200:
            print(f'  SO create failed: {r_so.status_code} {r_so.text[:300]}')
            results.append((order_num, '', '', '', 'SO_CREATE_FAIL'))
            continue
        so_name = r_so.json().get('data', {}).get('name', '')
        print(f'  SO created: {so_name}')

        r_sub = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, json={'docstatus': 1}, timeout=30)
        if r_sub.status_code != 200:
            print(f'  SO submit failed: {r_sub.status_code} {r_sub.text[:300]}')
            results.append((order_num, so_name, '', '', 'SO_SUBMIT_FAIL'))
            continue
        print(f'  SO submitted!')

        dn_name, awb, courier = process_order_with_so(order_num, so_name, [], shopify, is_ppcod, cod_amount)
        results.append((order_num, so_name, dn_name, awb, courier))
        continue

    print(f'  UNHANDLED CASE')
    results.append((order_num, '', '', '', 'UNHANDLED'))


# SUMMARY
print('\n\n' + '='*70)
print('FINAL SUMMARY')
print('='*70)
ok = fail = 0
for order_num, so, dn, awb, courier in results:
    if awb: ok += 1
    else: fail += 1
    print(f'{order_num:12s} | {so:15s} | {dn:20s} | {awb or "NO AWB":20s} | {courier}')
print(f'\n{ok} OK, {fail} FAILED out of {len(results)}')
