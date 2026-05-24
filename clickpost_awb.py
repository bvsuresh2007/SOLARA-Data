import requests, json, time
from dotenv import dotenv_values

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

# Clickpost creds from server script
CP_USERNAME = 'solara'
CP_API_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

# Shopify creds
r0 = s.get(f'{BASE}/api/resource/Shopify Setting/Shopify Setting', timeout=15)
sdata = r0.json()['data']
shop_url = sdata['shopify_url']
shop_token = sdata['password']
shopify_s = requests.Session()
shopify_s.headers.update({'X-Shopify-Access-Token': shop_token, 'Content-Type': 'application/json'})

dns_to_process = [
    ('SHPDN27-00906', 'SOL1193914', '6996804010216', '6366455070952'),
    ('SHPDN27-00018', 'SOL1193787', '6996453064936', '6366456152296'),
]

for dn_name, oid, shopify_order_id, fulfillment_id in dns_to_process:
    print(f'\n=== {oid} | DN: {dn_name} ===')

    # Get DN details
    r_dn = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', timeout=15)
    dn = r_dn.json()['data']

    # Get shipping address
    addr_name = dn.get('shipping_address_name', '')
    drop_name = dn.get('customer_name', '')
    drop_address = ''
    drop_city = ''
    drop_state = ''
    drop_pincode = ''
    drop_phone = ''
    drop_email = ''

    if addr_name:
        r_addr = s.get(f'{BASE}/api/resource/Address/{addr_name}', timeout=15)
        if r_addr.status_code == 200:
            addr = r_addr.json()['data']
            drop_name = addr.get('address_title', '') or drop_name
            drop_address = addr.get('address_line1', '')
            if addr.get('address_line2'):
                drop_address += ', ' + addr['address_line2']
            drop_city = addr.get('city', '')
            drop_state = addr.get('state', '')
            drop_pincode = addr.get('pincode', '')
            drop_phone = (addr.get('phone', '') or '').replace('+91', '').replace(' ', '').strip()
            drop_email = addr.get('email_id', '')

    print(f'  Ship to: {drop_name}, {drop_city}, {drop_state} {drop_pincode}')

    # Get SO name
    so_name = ''
    for item in dn.get('items', []):
        if item.get('against_sales_order'):
            so_name = item['against_sales_order']
            break
    print(f'  SO: {so_name}')

    # Get tax rates
    igst_rate = sgst_rate = cgst_rate = 0
    for tax in dn.get('taxes', []):
        desc = (tax.get('description', '') or '').upper()
        if 'IGST' in desc:
            igst_rate = tax.get('rate', 0)
        elif 'SGST' in desc:
            sgst_rate = tax.get('rate', 0)
        elif 'CGST' in desc:
            cgst_rate = tax.get('rate', 0)

    # Build items
    items = []
    total_weight = 0
    hsn_code = ''
    for item in dn.get('items', []):
        r_item = s.get(f'{BASE}/api/resource/Item/{item["item_code"]}', params={
            'fields': json.dumps(['weight_per_unit', 'gst_hsn_code'])
        }, timeout=15)
        idata = r_item.json()['data'] if r_item.status_code == 200 else {}
        wt_kg = float(idata.get('weight_per_unit', 0) or 0)
        wt_g = int(wt_kg * 1000) if wt_kg else 0
        item_hsn = item.get('gst_hsn_code', '') or idata.get('gst_hsn_code', '') or ''
        if not hsn_code and item_hsn:
            hsn_code = item_hsn

        items.append({
            'sku': item['item_code'],
            'description': item.get('item_name', ''),
            'quantity': int(item['qty']),
            'price': float(item['rate']),
            'gst_info': {
                'seller_gstin': '36AADCW0665P1ZS',
                'taxable_value': round(float(item.get('net_amount', 0) or item.get('amount', 0)), 2),
                'hsn_code': str(item_hsn),
                'igst_tax_rate': float(igst_rate),
                'sgst_tax_rate': float(sgst_rate),
                'cgst_tax_rate': float(cgst_rate)
            },
            'additional': {}
        })
        if wt_g > 0:
            items[-1]['additional']['weight'] = wt_g * int(item['qty'])
            total_weight += wt_g * int(item['qty'])

    if total_weight <= 0:
        total_weight = 2000

    label_reference = oid

    # Step 1: Recommendation API
    print(f'  Calling Clickpost Recommendation API...')
    rec_url = f'https://www.clickpost.in/api/v1/recommendation_api/?key={CP_API_KEY}'
    rec_payload = [{
        'pickup_pincode': '501218',
        'drop_pincode': drop_pincode,
        'order_type': 'PREPAID',
        'reference_number': label_reference,
        'item': ', '.join([i['description'] for i in items]),
        'invoice_value': float(dn['grand_total']),
        'delivery_type': 'FORWARD',
        'weight': int(total_weight),
        'height': 15, 'length': 30, 'breadth': 20
    }]

    r_rec = requests.post(rec_url, json=rec_payload, headers={'Content-Type': 'application/json'}, timeout=30)
    rec_resp = r_rec.json()

    cp_id = 4  # Delhivery fallback
    cp_name = 'Delhivery'
    account_code = ''

    if rec_resp.get('meta', {}).get('success'):
        result = rec_resp.get('result', [])
        if result and result[0].get('pincode_serviceable'):
            pref = result[0].get('preference_array', [])
            if pref:
                top = pref[0]
                cp_id = top.get('cp_id', 4)
                cp_name = top.get('cp_name', '') or top.get('courier_name', '') or 'Delhivery'
                account_code = top.get('account_code', '')
                print(f'  Recommended: {cp_name} (cp_id={cp_id})')
        else:
            print(f'  Pincode {drop_pincode} not serviceable via recommendation, trying fallback Delhivery (cp_id=4)')
            cp_id = 4
            cp_name = 'Delhivery'
    else:
        print(f'  Recommendation failed, using fallback Delhivery')

    # Step 2: Order Creation API
    print(f'  Calling Clickpost Order Creation API...')
    pickup_time = '2026-04-07T10:00:00+05:30'

    payload = {
        'pickup_info': {
            'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana',
            'pickup_pincode': '501218', 'pickup_country': 'IN',
            'pickup_address': '7-71/7 Thondupally ORR Service Road Shamshabad Mandal',
            'pickup_name': 'SOLARA WIN SURFACE', 'pickup_phone': '9769634812',
            'email': 'pawool.kumar@solara.in', 'pickup_time': pickup_time
        },
        'drop_info': {
            'drop_name': drop_name, 'drop_address': drop_address,
            'drop_city': drop_city, 'drop_state': drop_state,
            'drop_pincode': drop_pincode, 'drop_country': 'IN',
            'drop_phone': drop_phone, 'drop_email': drop_email
        },
        'shipment_details': {
            'courier_partner': cp_id, 'reference_number': label_reference,
            'order_type': 'PREPAID', 'invoice_value': float(dn['grand_total']),
            'invoice_number': dn_name, 'invoice_date': str(dn['posting_date']),
            'cod_value': 0, 'weight': int(total_weight),
            'height': 15, 'breadth': 20, 'length': 30, 'items': items
        },
        'gst_info': {
            'seller_gstin': '36AADCW0665P1ZS',
            'taxable_value': float(dn['net_total']),
            'hsn_code': hsn_code,
            'igst_tax_rate': float(igst_rate),
            'sgst_tax_rate': float(sgst_rate),
            'cgst_tax_rate': float(cgst_rate)
        },
        'additional': {
            'label': True,
            'return_info': {
                'pincode': '501218', 'name': 'SOLARA WIN SURFACE',
                'address': '7-71/7 Thondupally ORR Service Road Shamshabad Mandal',
                'phone': '9769634812', 'city': 'Hyderabad', 'state': 'Telangana', 'country': 'IN'
            }
        }
    }
    if account_code:
        payload['additional']['account_code'] = account_code

    create_url = f'https://www.clickpost.in/api/v3/create-order/?username={CP_USERNAME}&key={CP_API_KEY}'
    r_create = requests.post(create_url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
    create_resp = r_create.json()

    if create_resp.get('meta', {}).get('success'):
        result = create_resp.get('result', {})
        awb = result.get('waybill', '')
        print(f'  AWB: {awb} via {cp_name}')

        # Update DN in Atlas
        tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
        label_url = result.get('label', '')
        r_upd = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', json={
            'awb_number': awb,
            'courier_partner': cp_name,
            'shipment_status': 'Created',
            'tracking_url': tracking_url,
            'clickpost_order_id': str(cp_id),
            'shipping_label': label_url
        }, timeout=15)
        print(f'  DN updated: {r_upd.status_code}')

        # Update Shopify fulfillment with tracking
        courier_map = {
            'Delhivery': 'Delhivery', 'Bluedart': 'Bluedart', 'Blue Dart': 'Bluedart',
            'DTDC': 'DTDC Express', 'Xpressbees': 'XpressBees', 'Ecom Express': 'Ecom Express',
        }
        tracking_company = courier_map.get(cp_name, cp_name)

        r_shopify = shopify_s.post(
            f'https://{shop_url}/admin/api/2024-01/fulfillments/{fulfillment_id}/update_tracking.json',
            json={
                'fulfillment': {
                    'tracking_info': {
                        'number': str(awb),
                        'url': tracking_url,
                        'company': tracking_company
                    },
                    'notify_customer': True
                }
            }, timeout=15)
        print(f'  Shopify tracking update: {r_shopify.status_code}')
        if r_shopify.status_code not in (200, 201):
            print(f'  Shopify error: {r_shopify.text[:200]}')
    else:
        err = create_resp.get('meta', {}).get('message', 'Unknown error')
        print(f'  Clickpost FAILED: {err}')
        print(f'  Full response: {json.dumps(create_resp, indent=2)[:500]}')

    time.sleep(1)

print('\n=== DONE ===')
