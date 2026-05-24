import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

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

# Group D: Ghost SKU fix
# Order -> (sol, so_name, child_name, correct_sku, otype)
orders = [
    ('SOL1201460', 'SHP27-07636', '4f6j68307t', 'SOL-MBL-COM-IVR-P13', 'PPCOD'),
    ('SOL1203802', 'SHP27-10109', 'f2acnac243', 'SOL-AF-MITTEN', 'Prepaid'),
    ('SOL1204601', 'SHP27-10904', 'ff5vq04fsg', 'SOL-SS-COM-302', 'Prepaid'),
]

results = []

for sol, so_name, child_name, correct_sku, otype in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} | Fix ghost: {correct_sku} ===')

    # Step 1: Fix ghost SKU on SO
    print(f'  1. Fixing ghost SKU: child={child_name} -> {correct_sku}')
    sn = 'tmp_fixsku_' + sol.lower()
    script = (
        "frappe.db.set_value('Sales Order Item','" + child_name + "','item_code','" + correct_sku + "',update_modified=False)\n"
        "frappe.db.set_value('Sales Order Item','" + child_name + "','item_name','" + correct_sku + "',update_modified=False)\n"
        "frappe.db.commit()\n"
        "frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    print(f'    Result: {msg}')

    # Step 2: Get full SO details
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full = r_so.json().get('data', {})
    customer = so_full.get('customer', '')
    shopify_oid = so_full.get('shopify_order_id', '')
    addr_name = so_full.get('shipping_address_name', '')
    cod_amount = float(so_full.get('custom_cod_amount', 0) or 0)

    # Fix PPCOD COD=0 if needed
    if otype == 'PPCOD' and cod_amount == 0:
        r_txn = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/transactions.json', headers=SHOP_H, timeout=15)
        txns = r_txn.json().get('transactions', [])
        captured = sum(float(t.get('amount','0')) for t in txns if t.get('kind') in ('capture','sale') and t.get('status') == 'success')
        total = float(so_full.get('grand_total', 0))
        cod_amount = round(total - captured, 2)
        if cod_amount > 0:
            print(f'  Fixing PPCOD COD: 0 -> {cod_amount}')
            sn2 = 'tmp_fixcod_' + sol.lower()
            script2 = "frappe.db.set_value('Sales Order','" + so_name + "','custom_cod_amount'," + str(cod_amount) + ",update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
            run_server_script(sn2, script2)

    # Check address — also verify PIN matches Shopify
    r_sh = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
    sh_order = r_sh.json().get('order', {})
    sa = sh_order.get('shipping_address') or {}
    sh_pin = str(sa.get('zip', ''))

    # Check atlas address PIN
    atlas_pin = ''
    if addr_name:
        r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H,
            params={'fields': json.dumps(['pincode'])}, timeout=10)
        atlas_pin = str(r_a.json().get('data', {}).get('pincode', ''))

    if atlas_pin != sh_pin:
        print(f'  PIN mismatch: atlas={atlas_pin} shopify={sh_pin} — fixing address')
        # Create address from Shopify
        sh_addr1 = sa.get('address1', '') or ''
        sh_addr2 = sa.get('address2', '') or ''
        sh_city = sa.get('city', '') or ''
        sh_state = sa.get('province', '') or ''
        sh_name = sa.get('name', '') or ''
        sh_phone = sa.get('phone', '') or ''
        phone = sh_phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(phone) > 10: phone = phone[-10:]

        new_addr = customer + '-' + sol + '-Shipping'
        requests.delete(f'{BASE}/api/resource/Address/{new_addr}', headers=H, timeout=10)
        time.sleep(0.5)
        r_na = requests.post(f'{BASE}/api/resource/Address', headers=H, json={
            'name': new_addr, 'address_title': sh_name or customer, 'address_type': 'Shipping',
            'address_line1': sh_addr1 or 'NA', 'address_line2': sh_addr2,
            'city': sh_city or 'NA', 'state': sh_state, 'pincode': sh_pin,
            'country': 'India', 'phone': phone, 'email_id': sh_order.get('email', '') or '',
            'links': [{'link_doctype': 'Customer', 'link_name': customer}],
        }, timeout=15)
        if r_na.status_code in (200, 201):
            addr_name = r_na.json().get('data', {}).get('name', new_addr)
        else:
            addr_name = new_addr
        # Update SO
        sn3 = 'tmp_fixaddr_' + sol.lower()
        script3 = "frappe.db.set_value('Sales Order','" + so_name + "','shipping_address_name','" + addr_name + "',update_modified=False)\nfrappe.db.set_value('Sales Order','" + so_name + "','customer_address','" + addr_name + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
        run_server_script(sn3, script3)
        print(f'  Address fixed: {addr_name}')

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
        if res_list: pref = res_list[0].get('preference_array', [])
    courier_ids = [p.get('cp_id', 0) for p in pref]
    courier_names = [p.get('courier_name', '') for p in pref]
    print(f'  Serviceable PIN={sh_pin}: {courier_names}')

    if not courier_ids:
        print(f'  NOT SERVICEABLE — skipping')
        results.append((sol, 'NOT_SERVICEABLE', '', '', '', sh_pin))
        continue

    # Step 3: Re-read SO items (now with fixed SKU)
    r_so2 = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    so_full2 = r_so2.json().get('data', {})

    dn_items = []
    for it in so_full2.get('items', []):
        ic = it.get('item_code', '') or ''
        if not ic:
            print(f'  WARNING: still ghost item: {it.get("item_name","")}')
            continue
        dn_items.append({
            'item_code': ic,
            'qty': it.get('qty', 0),
            'rate': it.get('rate', 0),
            'against_sales_order': so_name,
            'so_detail': it.get('name', ''),
            'warehouse': it.get('warehouse', 'Main Warehouse - WTBBPL'),
        })

    item_strs = [it['item_code'] + ' x' + str(int(it['qty'])) for it in dn_items]
    print(f'  DN items: {", ".join(item_strs)}')

    # Step 4: Create DN
    dn_payload = {
        'customer': customer,
        'shopify_order_id': shopify_oid,
        'shopify_order_number': sol,
        'custom_shopify_order_number': sol,
        'shipping_address_name': addr_name,
        'customer_address': addr_name,
        'custom_order_type': otype,
        'items': dn_items,
        'taxes_and_charges': so_full2.get('taxes_and_charges', ''),
    }
    if otype == 'PPCOD' and cod_amount > 0:
        dn_payload['custom_cod_amount'] = cod_amount

    print(f'  Creating DN...')
    r_dn = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_payload, timeout=30)
    if r_dn.status_code not in (200, 201):
        print(f'  DN FAIL: {r_dn.status_code} {r_dn.text[:300]}')
        results.append((sol, 'FAIL', '', '', '', 'DN create failed'))
        continue

    new_dn = r_dn.json().get('data', {}).get('name', '')
    print(f'  DN: {new_dn}')

    # Step 5: Submit DN
    print(f'  Submitting...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, json={'docstatus': 1}, timeout=60)

    awb = ''
    courier = ''
    if r_sub.status_code == 200:
        dn_data = r_sub.json().get('data', {})
        awb = dn_data.get('awb_number', '') or ''
        courier = dn_data.get('courier_partner', '') or ''
        print(f'  Submitted | AWB={awb} | {courier}')
    else:
        time.sleep(2)
        r_chk = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
            params={'fields': json.dumps(['docstatus','awb_number','courier_partner'])}, timeout=15)
        d2 = r_chk.json().get('data', {})
        if d2.get('docstatus') == 1:
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
            print(f'  Submitted (race) | AWB={awb} | {courier}')
        else:
            print(f'  Submit FAIL: {r_sub.status_code} {r_sub.text[:300]}')
            results.append((sol, 'FAIL', new_dn, '', '', 'Submit failed'))
            continue

    # Check AWB after delay
    if not awb:
        time.sleep(3)
        r_chk2 = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H,
            params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
        d3 = r_chk2.json().get('data', {})
        awb = d3.get('awb_number', '') or ''
        courier = d3.get('courier_partner', '') or ''
        if awb:
            print(f'  AWB (delayed): {awb} via {courier}')

    # Manual Clickpost if no AWB — Delhivery first, Bluedart fallback
    if not awb:
        print(f'  No auto AWB — trying manual Clickpost (Delhivery first)...')
        r_a2 = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
        addr_data = r_a2.json().get('data', {})
        drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip()
        a_phone = str(addr_data.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(a_phone) > 10: a_phone = a_phone[-10:]

        r_dn_full = requests.get(f'{BASE}/api/resource/Delivery Note/{new_dn}', headers=H, timeout=15)
        dn_full = r_dn_full.json().get('data', {})
        items_list = dn_full.get('items', [])
        total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
        if total_weight <= 0: total_weight = len(items_list) * 0.5
        total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
        if total_weight_g < 200: total_weight_g = 500
        grand_total = max(float(dn_full.get('grand_total', 0) or 0), 1.0)

        order_type = 'PREPAID'
        cod_value = 0
        if otype in ('PPCOD', 'COD'):
            order_type = 'COD'
            cod_value = cod_amount

        # Delhivery first (4), then Bluedart (5)
        cp_try = [cp for cp in [4, 5] if cp in courier_ids]
        if not cp_try:
            cp_try = courier_ids
        cp_names_map = {4: 'Delhivery', 5: 'Bluedart'}

        for cp_id in cp_try:
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
                    'order_type': order_type, 'invoice_value': grand_total, 'reference_number': sol,
                    'length': 30, 'breadth': 20, 'height': 15, 'weight': total_weight_g,
                    'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                               'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                    'delivery_type': 'FORWARD', 'cod_value': cod_value, 'courier_partner': cp_id,
                    'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''),
                },
                'gst_info': {
                    'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': float(dn_full.get('net_total', 0) or 0),
                    'is_seller_registered_under_gst': True, 'place_of_supply': addr_data.get('state', ''),
                    'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
                    'sgst_amount': 0, 'cgst_amount': 0,
                    'igst_amount': float(dn_full.get('total_taxes_and_charges', 0) or 0),
                    'invoice_number': new_dn, 'invoice_date': dn_full.get('posting_date', ''),
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
            print(f'  Trying {cname}...')
            r_cp = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
            cp_resp = r_cp.json()
            meta = cp_resp.get('meta', {})
            if meta.get('success') and meta.get('status') == 200:
                awb = str(cp_resp.get('result', {}).get('waybill', ''))
                courier = cname
                print(f'  AWB={awb} via {courier}')
                # Save to DN
                sn_awb = 'tmp_nawb_' + new_dn.replace('-','_').lower()
                script_awb = "frappe.db.set_value('Delivery Note','" + new_dn + "','awb_number','" + awb + "',update_modified=False)\nfrappe.db.set_value('Delivery Note','" + new_dn + "','courier_partner','" + courier + "',update_modified=False)\nfrappe.db.commit()\nfrappe.response['message']='ok'"
                run_server_script(sn_awb, script_awb)
                print(f'  AWB saved to DN')
                break
            else:
                print(f'  FAIL {cname}: {meta.get("message","")[:150]}')

    if not awb:
        print(f'  ALL FAILED — no AWB')
        results.append((sol, 'NO_AWB', new_dn, '', '', otype))
        continue

    # Shopify fulfillment
    if shopify_oid:
        tracking_url = 'https://www.clickpost.in/tracking/#/' + awb
        r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
        existing = r_ful.json().get('fulfillments', [])
        if existing:
            ful_id = str(existing[-1].get('id', ''))
            payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'  Shopify tracking: {r_u.status_code}')
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
                    'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
                r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=payload, timeout=30)
                if r_f.status_code in (200, 201):
                    print(f'  Shopify fulfillment created')
                else:
                    print(f'  Shopify FAIL: {r_f.status_code} {r_f.text[:150]}')
            else:
                print(f'  No open FOs')

    results.append((sol, 'OK', new_dn, awb, courier, otype))
    time.sleep(1)

print(f'\n\n{"="*80}')
print(f'GROUP D FIX SUMMARY')
print(f'{"="*80}')
for r in results:
    if r[1] == 'OK':
        print(f'  OK   {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]} | {r[5]}')
    else:
        print(f'  FAIL {r[0]}: {r[1]} | {r[5]}')
