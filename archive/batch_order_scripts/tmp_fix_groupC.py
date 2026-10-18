import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'    Script create FAIL: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(3)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'    Script error: {exc[:300]}')
        return None
    return msg

state_map = {
    'Uttar Pradesh': 'Uttar Pradesh', 'Maharashtra': 'Maharashtra', 'Tamil Nadu': 'Tamil Nadu',
    'Karnataka': 'Karnataka', 'Telangana': 'Telangana', 'Gujarat': 'Gujarat',
    'West Bengal': 'West Bengal', 'Rajasthan': 'Rajasthan', 'Delhi': 'Delhi',
    'Puducherry': 'Puducherry', 'Uttarakhand': 'Uttarakhand', 'Sikkim': 'Sikkim',
    'Manipur': 'Manipur', 'Meghalaya': 'Meghalaya', 'Mizoram': 'Mizoram',
    'Nagaland': 'Nagaland', 'Arunachal Pradesh': 'Arunachal Pradesh',
    'Andhra Pradesh': 'Andhra Pradesh', 'Punjab': 'Punjab', 'Haryana': 'Haryana',
    'Kerala': 'Kerala', 'Bihar': 'Bihar', 'Madhya Pradesh': 'Madhya Pradesh',
    'Jharkhand': 'Jharkhand', 'Odisha': 'Odisha', 'Chhattisgarh': 'Chhattisgarh',
    'Assam': 'Assam', 'Goa': 'Goa', 'Himachal Pradesh': 'Himachal Pradesh',
    'Jammu and Kashmir': 'Jammu and Kashmir', 'Jammu & Kashmir': 'Jammu and Kashmir',
    'Chandigarh': 'Chandigarh', 'Tripura': 'Tripura',
    'Dadra and Nagar Haveli': 'Dadra and Nagar Haveli',
    'Andaman and Nicobar Islands': 'Andaman and Nicobar Islands',
    'Lakshadweep': 'Lakshadweep', 'Ladakh': 'Ladakh',
}

# Group C: PIN mismatch — fix address from Shopify, delete draft DNs, create new DN, submit
# SOL -> (SO name, Shopify PIN)
orders = [
    ('SOL1201081', 'SHP27-07259', 'PPCOD'),
    ('SOL1202422', 'SHP27-08669', 'PPCOD'),
    ('SOL1204428', 'SHP27-10729', 'PPCOD'),
    ('SOL1201638', 'SHP27-07835', 'Prepaid'),
    ('SOL1202032', 'SHP27-08264', 'Prepaid'),
    ('SOL1202958', 'SHP27-09253', 'Prepaid'),
    ('SOL1203343', 'SHP27-09651', 'Prepaid'),
    ('SOL1202753', 'SHP27-09052', 'Prepaid'),
    ('SOL1203337', 'SHP27-09645', 'Prepaid'),
    ('SOL1204204', 'SHP27-10506', 'Prepaid'),
    ('SOL1201694', 'SHP27-07892', 'Prepaid'),
    ('SOL1202356', 'SHP27-08606', 'Prepaid'),
]

results = []

for sol, so_name, otype in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} | {so_name} | {otype} ===')

    # Get SO full details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so.json().get('data', {})
    customer = so_full.get('customer', '')
    shopify_oid = so_full.get('shopify_order_id', '')
    cod_amount = float(so_full.get('custom_cod_amount', 0) or 0)

    # Get Shopify shipping address (source of truth)
    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    sh_order = r_sh.json().get('order', {})
    sa = sh_order.get('shipping_address') or {}
    sh_pin = str(sa.get('zip', ''))
    sh_addr1 = sa.get('address1', '') or ''
    sh_addr2 = sa.get('address2', '') or ''
    sh_city = sa.get('city', '') or ''
    sh_state = sa.get('province', '') or ''
    sh_name = sa.get('name', '') or ''
    sh_phone = sa.get('phone', '') or ''

    phone = sh_phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(phone) > 10:
        phone = phone[-10:]
    atlas_state = state_map.get(sh_state, sh_state)

    print(f'  Shopify: {sh_name} | {sh_city} {atlas_state} PIN={sh_pin} | Phone={phone}')

    # Fix PPCOD COD=0 if needed
    if otype == 'PPCOD' and cod_amount == 0:
        r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
        txns = r_txn.json().get('transactions', [])
        captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
        total = float(so_full.get('grand_total', 0))
        cod_amount = round(total - captured, 2)
        if cod_amount > 0:
            print(f'  Fixing PPCOD COD: 0 -> {cod_amount}')
            sn = 'tmp_fixcod_' + sol.lower()
            script = "frappe.db.set_value('Sales Order','" + so_name + "','custom_cod_amount'," + str(cod_amount) + ",update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
            run_server_script(sn, script)

    # Check serviceability
    cp_otype = 'COD' if otype == 'PPCOD' else 'PREPAID'
    cod_v = cod_amount if cp_otype == 'COD' else 0
    r_svc = requests.post('https://www.clickpost.in/api/v1/recommendation_api/',
        params={'key': CP_KEY},
        json=[{'reference_number': '1', 'pickup_pincode': '501218', 'drop_pincode': sh_pin,
               'order_type': cp_otype, 'delivery_type': 'FORWARD', 'invoice_value': float(so_full.get('grand_total', 1000)),
               'length': 30, 'breadth': 20, 'height': 15, 'weight': 500, 'item': 'DGS',
               'cod_value': cod_v}],
        timeout=15)
    svc_data = r_svc.json()
    pref = []
    if svc_data.get('meta', {}).get('success'):
        res_list = svc_data.get('result', [])
        if res_list and isinstance(res_list, list):
            pref = res_list[0].get('preference_array', [])
    courier_ids = [p.get('cp_id', 0) for p in pref]
    courier_names = [p.get('courier_name', '') for p in pref]

    if not courier_ids:
        print(f'  NOT SERVICEABLE for Shopify PIN={sh_pin} — skipping')
        results.append((sol, 'NOT_SERVICEABLE', '', '', '', sh_pin))
        continue

    print(f'  Serviceable: {courier_names}')

    # Step 1: Create/update Address from Shopify
    addr_name = customer + '-' + sol + '-Shipping'
    requests.delete(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=10)
    time.sleep(0.5)

    addr_payload = {
        'name': addr_name,
        'address_title': sh_name or customer,
        'address_type': 'Shipping',
        'address_line1': sh_addr1 or 'NA',
        'address_line2': sh_addr2,
        'city': sh_city or 'NA',
        'state': atlas_state,
        'pincode': sh_pin,
        'country': 'India',
        'phone': phone,
        'email_id': sh_order.get('email', '') or '',
        'links': [{'link_doctype': 'Customer', 'link_name': customer}],
    }
    r_addr = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
    if r_addr.status_code in (200, 201):
        created_addr = r_addr.json().get('data', {}).get('name', addr_name)
        print(f'  Address: {created_addr}')
    else:
        # Try find existing
        r_find = requests.get(f'{BASE}/api/resource/Address', headers=H,
            params={'filters': json.dumps([['name','like',f'%{sol}%Shipping%']]),
                    'fields': json.dumps(['name']), 'limit_page_length': 1}, timeout=10)
        found = r_find.json().get('data', [])
        if found:
            created_addr = found[0]['name']
            requests.put(f'{BASE}/api/resource/Address/{created_addr}', headers=H, json={
                'address_line1': sh_addr1 or 'NA', 'address_line2': sh_addr2,
                'city': sh_city or 'NA', 'state': atlas_state, 'pincode': sh_pin, 'phone': phone
            }, timeout=15)
            print(f'  Updated existing: {created_addr}')
        else:
            print(f'  Address FAIL: {r_addr.status_code} {r_addr.text[:200]}')
            results.append((sol, 'FAIL', '', '', '', 'Address failed'))
            continue

    # Step 2: Update SO shipping address
    sn = 'tmp_fixaddr_' + sol.lower()
    script = "frappe.db.set_value('Sales Order','" + so_name + "','shipping_address_name','" + created_addr + "',update_modified=False)\nfrappe.db.set_value('Sales Order','" + so_name + "','customer_address','" + created_addr + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
    msg = run_server_script(sn, script)
    if msg:
        print(f'  SO address updated')

    # Step 3: Delete all existing draft DNs for this order
    r_dns = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['custom_shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 20}, timeout=15)
    draft_dns = r_dns.json().get('data', [])
    # Also check by shopify_order_number
    r_dns2 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name']),
                'limit_page_length': 20}, timeout=15)
    draft_dns2 = r_dns2.json().get('data', [])
    all_draft_names = set(d['name'] for d in draft_dns + draft_dns2)

    for dn_name in all_draft_names:
        r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=10)
        print(f'  Deleted draft DN: {dn_name} ({r_del.status_code})')
    time.sleep(0.5)

    # Step 4: Re-read SO items
    r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full2 = r_so2.json().get('data', {})

    dn_items = []
    for it in so_full2.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic:
            continue
        dn_items.append({
            'item_code': ic,
            'qty': it.get('qty', 0),
            'rate': it.get('rate', 0),
            'against_sales_order': so_name,
            'so_detail': it.get('name', ''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
        })

    if not dn_items:
        print(f'  NO ITEMS on SO — skipping')
        results.append((sol, 'FAIL', '', '', '', 'No items'))
        continue

    # Step 5: Create new DN with correct address
    dn_payload = {
        'customer': customer,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': created_addr,
        'customer_address': created_addr,
        'custom_order_type': otype,
        'items': dn_items,
        'taxes_and_charges': so_full2.get('taxes_and_charges', ''),
    }
    if otype == 'PPCOD' and cod_amount > 0:
        dn_payload['custom_cod_amount'] = cod_amount

    print(f'  Creating new DN...')
    r_dn = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn.status_code not in (200, 201):
        print(f'  DN create FAIL: {r_dn.status_code} {r_dn.text[:300]}')
        results.append((sol, 'FAIL', '', '', '', 'DN create failed'))
        continue

    new_dn = r_dn.json().get('data', {}).get('name', '')
    print(f'  DN: {new_dn}')

    # Step 6: Submit DN
    print(f'  Submitting DN...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}',
        headers=H, json={'docstatus': 1}, timeout=60)

    if r_sub.status_code == 200:
        dn_data = r_sub.json().get('data', {})
        awb = dn_data.get('awb_number', '') or ''
        courier = dn_data.get('courier_partner', '') or ''
        print(f'  Submitted | AWB={awb} | Courier={courier}')
    else:
        # Check if it actually submitted (PostingTime race)
        time.sleep(2)
        r_check = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
            params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
        d2 = r_check.json().get('data', {})
        if d2.get('docstatus') == 1:
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
            print(f'  Submitted (race OK) | AWB={awb} | Courier={courier}')
        else:
            print(f'  Submit FAIL: {r_sub.status_code} {r_sub.text[:300]}')
            results.append((sol, 'FAIL', new_dn, '', '', 'Submit failed'))
            continue

    # Check AWB after delay if empty
    if not awb:
        time.sleep(3)
        r_check2 = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
            params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
        d3 = r_check2.json().get('data', {})
        awb = d3.get('awb_number', '') or ''
        courier = d3.get('courier_partner', '') or ''
        if awb:
            print(f'  AWB (delayed): {awb} via {courier}')

    if not awb:
        # Try manual Clickpost — force Bluedart first, then Delhivery
        print(f'  No AWB from auto — trying manual Clickpost...')
        addr_data = {}
        try:
            r_a = requests.get(f'{BASE}/api/resource/Address/{created_addr}', headers=H, timeout=15)
            addr_data = r_a.json().get('data', {})
        except:
            pass

        drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip()
        a_phone = str(addr_data.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(a_phone) > 10: a_phone = a_phone[-10:]

        # Re-read DN for items
        r_dn_full = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, timeout=15)
        dn_full = r_dn_full.json().get('data', {})
        items_list = dn_full.get('items', [])
        total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
        if total_weight <= 0: total_weight = len(items_list) * 0.5
        total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
        if total_weight_g < 200: total_weight_g = 500
        grand_total = max(float(dn_full.get('grand_total', 0) or 0), 1.0)

        # Count cancelled DNs for ref suffix
        r_cdn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['custom_shopify_order_number','=',sol],['docstatus','=',2]]),
                    'fields': json.dumps(['name']), 'limit_page_length': 0}, timeout=10)
        cancelled_count = len(r_cdn.json().get('data', []))
        ref = sol if cancelled_count == 0 else sol + '-R' + str(cancelled_count)

        order_type = 'PREPAID'
        cod_value = 0
        if otype in ('PPCOD', 'COD'):
            order_type = 'COD'
            cod_value = cod_amount

        cp_try_order = sorted(courier_ids, key=lambda x: 0 if x == 5 else 1)
        cp_names_map = {4: 'Delhivery', 5: 'Bluedart'}

        for cp_id in cp_try_order:
            cp_payload = {
                'pickup_info': {
                    'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                    'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                    'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-12T10:00:00Z',
                },
                'drop_info': {
                    'drop_name': dn_full.get('customer_name', ''), 'drop_phone': a_phone,
                    'drop_address': drop_address, 'drop_city': addr_data.get('city', ''),
                    'drop_state': addr_data.get('state', ''), 'drop_pincode': sh_pin,
                    'drop_country': 'IN', 'drop_email': addr_data.get('email_id', '') or 'noreply@solara.in',
                },
                'shipment_details': {
                    'order_type': order_type, 'invoice_value': grand_total, 'reference_number': ref,
                    'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                    'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                               'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                    'delivery_type': 'FORWARD', 'cod_value': cod_value, 'courier_partner': cp_id,
                    'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''),
                },
                'gst_info': {
                    'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(dn_full.get('net_total', 0) or 0),
                    'ewaybill_serial_number': '', 'is_seller_registered_under_gst': True,
                    'place_of_supply': addr_data.get('state', ''), 'cstin': '',
                    'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                    'sgst_amount': 0, 'cgst_amount': 0,
                    'igst_amount': float(dn_full.get('total_taxes_and_charges', 0) or 0),
                    'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''), 'hsn_code': '',
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

            cname = cp_names_map.get(cp_id, str(cp_id))
            print(f'  Trying {cname} (cp_id={cp_id})...')
            r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
            cp_resp = r_cp.json()
            meta = cp_resp.get('meta', {})

            if meta.get('success') and meta.get('status') == 200:
                awb = str(cp_resp.get('result', {}).get('waybill', ''))
                courier = cname
                print(f'  AWB={awb} via {courier}')

                # Save to DN
                sn2 = 'tmp_nawb_' + new_dn.replace('-','_').lower()
                script2 = "frappe.db.set_value('Delivery Note','" + new_dn + "','awb_number','" + awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + new_dn + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
                run_server_script(sn2, script2)
                print(f'  AWB saved to DN')
                break
            else:
                err = meta.get('message', '')
                print(f'  FAIL {cname}: {err[:150]}')

    if not awb:
        print(f'  ALL FAILED — no AWB')
        results.append((sol, 'NO_AWB', new_dn, '', '', otype))
        continue

    # Sync Shopify fulfillment
    if shopify_oid:
        tracking_url = 'https://www.clickpost.in/tracking/#/' + awb
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        existing = r_ful.json().get('fulfillments', [])

        if existing:
            ful_id = str(existing[-1].get('id', ''))
            payload = {'fulfillment': {
                'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                headers=SHOP_H, json=payload, timeout=15)
            if r_u.status_code in (200, 201):
                print(f'  Shopify tracking updated')
            else:
                print(f'  Shopify tracking FAIL: {r_u.status_code} {r_u.text[:150]}')
        else:
            r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
            fos = r_fo.json().get('fulfillment_orders', [])
            open_fos = []
            for fo in fos:
                if fo.get('status') in ('open', 'in_progress'):
                    fo_items = [{'id': li['id'], 'quantity': li.get('fulfillable_quantity', 0)}
                               for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
                    if fo_items:
                        open_fos.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_items})
            if open_fos:
                payload = {'fulfillment': {'line_items_by_fulfillment_order': open_fos,
                    'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                    'notify_customer': True}}
                r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
                if r_f.status_code in (200, 201):
                    print(f'  Shopify fulfillment created')
                else:
                    print(f'  Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:150]}')
            else:
                print(f'  No open FOs on Shopify')

    results.append((sol, 'OK', new_dn, awb, courier, otype))
    time.sleep(1)

# Summary
print(f'\n\n{"="*80}')
print(f'GROUP C FIX SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] not in ('OK', 'NOT_SERVICEABLE')]
ns = [r for r in results if r[1] == 'NOT_SERVICEABLE']
for r in ok:
    print(f'  OK   {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]} | {r[5]}')
for r in fail:
    print(f'  FAIL {r[0]}: DN={r[2]} | {r[5]}')
for r in ns:
    print(f'  N/S  {r[0]}: PIN={r[5]}')
print(f'\n  Total: {len(ok)} OK | {len(fail)} FAIL | {len(ns)} not serviceable')
