import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'    Script create failed: {r.status_code} {r.text[:200]}')
        return None
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

orders = [
    # (sol, so_name, shopify_oid, existing_submitted_dn, existing_draft_dns)
    ('SOL1206120', 'SHP27-12423', '7086695416040', 'SHPDN27-14979', []),
    ('SOL1207613', 'SHP27-13905', '7094064808168', 'SHPDN27-16223', ['SHPDN27-16176', 'SHPDN27-16219']),
    ('SOL1207230', 'SHP27-13519', '7092094501096', None, ['SHPDN27-15968']),
]

results = []

for sol, so_name, shopify_oid, submitted_dn, draft_dns in orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} ===')

    # Step 1: Pull Shopify shipping address
    r = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H,
        params={'fields': 'id,name,shipping_address'}, timeout=30)
    sa = r.json().get('order', {}).get('shipping_address', {})
    s_name = sa.get('name', '')
    s_addr1 = sa.get('address1', '')
    s_addr2 = sa.get('address2', '')
    s_city = sa.get('city', '')
    s_state = sa.get('province', '')
    s_zip = str(sa.get('zip', '')).strip()
    s_phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(s_phone) > 10: s_phone = s_phone[-10:]
    s_email = sa.get('email', '') or 'noreply@solara.in'
    print(f'  Shopify: {s_name} | {s_addr1} | {s_city}, {s_state} {s_zip} | Ph: {s_phone}')

    # Step 2: Get SO customer
    r_so = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, params={
        'fields': json.dumps(['customer', 'customer_name'])
    }, timeout=15)
    cust = r_so.json().get('data', {}).get('customer', '')

    # Step 3: Create/update Address on Atlas
    addr_name = f'{cust}-{sol}-Shipping'
    r_ae = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr_payload = {
        'address_title': cust,
        'address_type': 'Shipping',
        'address_line1': s_addr1 or s_name,
        'address_line2': s_addr2 or '',
        'city': s_city or 'Unknown',
        'state': s_state or '',
        'pincode': s_zip,
        'country': 'India',
        'phone': s_phone,
        'email_id': s_email,
        'is_shipping_address': 1,
        'links': [{'link_doctype': 'Customer', 'link_name': cust}],
    }
    if r_ae.status_code == 200:
        r_au = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        addr_name = r_au.json().get('data', {}).get('name', addr_name) if r_au.status_code == 200 else addr_name
        print(f'  Address updated: {addr_name}')
    else:
        addr_payload['name'] = addr_name
        r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r_ac.status_code == 200:
            addr_name = r_ac.json().get('data', {}).get('name', addr_name)
            print(f'  Address created: {addr_name}')
        else:
            print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')

    # Step 4: Update SO shipping address via server script
    script = (
        f"frappe.db.set_value('Sales Order','{so_name}','shipping_address_name','{addr_name}',update_modified=False)\n"
        f"frappe.db.set_value('Sales Order','{so_name}','customer_address','{addr_name}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script(f'tmp_addr_{sol[-4:]}', script)
    print(f'  SO address updated: {msg}')

    # Step 5: Handle DN
    dn_name = submitted_dn

    if submitted_dn:
        # Update address on existing submitted DN
        script = (
            f"frappe.db.set_value('Delivery Note','{submitted_dn}','shipping_address_name','{addr_name}',update_modified=False)\n"
            f"frappe.db.set_value('Delivery Note','{submitted_dn}','customer_address','{addr_name}',update_modified=False)\n"
            f"frappe.db.commit()\n"
            f"frappe.response['message']='ok'"
        )
        msg = run_server_script(f'tmp_dna_{sol[-4:]}', script)
        print(f'  DN {submitted_dn} address updated: {msg}')
    else:
        # Delete draft DNs first
        for ddn in draft_dns:
            r_del = requests.delete(f'{BASE}/api/resource/Delivery Note/{ddn}', headers=H, timeout=15)
            print(f'  Deleted draft {ddn}: {r_del.status_code}')

        # Reset per_delivered if needed
        r_pd = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, params={
            'fields': json.dumps(['per_delivered'])
        }, timeout=15)
        per_del = float(r_pd.json().get('data', {}).get('per_delivered', 0) or 0)
        if per_del > 0:
            r_so_full = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
            so_data = r_so_full.json().get('data', {})
            lines = [f"frappe.db.set_value('Sales Order','{so_name}','per_delivered',0,update_modified=False)"]
            lines.append(f"frappe.db.set_value('Sales Order','{so_name}','status','To Deliver and Bill',update_modified=False)")
            for item in so_data.get('items', []):
                iname = item.get('name', '')
                lines.append(f"frappe.db.set_value('Sales Order Item','{iname}','delivered_qty',0,update_modified=False)")
            lines.append("frappe.db.commit()")
            lines.append("frappe.response['message']='ok'")
            msg = run_server_script(f'tmp_rst_{sol[-4:]}', "\n".join(lines))
            print(f'  Reset per_delivered: {msg}')

        # Create DN from SO
        r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
            headers=H, params={'source_name': so_name}, timeout=15)
        if r_dn.status_code != 200:
            print(f'  make_delivery_note failed: {r_dn.status_code}')
            results.append((sol, '', '', 'DN_MAKE_FAIL'))
            continue
        dn_draft = r_dn.json().get('message', {})
        if not dn_draft.get('items'):
            print(f'  No items in DN draft!')
            results.append((sol, '', '', 'NO_ITEMS'))
            continue
        dn_draft['shipping_address_name'] = addr_name
        dn_draft['customer_address'] = addr_name
        dn_draft['shopify_order_id'] = shopify_oid
        dn_draft['shopify_order_number'] = sol
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
            results.append((sol, '', '', 'DN_SAVE_FAIL'))
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
                results.append((sol, dn_name, '', 'DN_SUBMIT_FAIL'))
                continue
        else:
            print(f'  DN submit failed: {r4.status_code} {r4.text[:300]}')
            results.append((sol, dn_name, '', 'DN_SUBMIT_FAIL'))
            continue

    # Step 6: Check AWB
    time.sleep(3)
    r6 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner'])
    }, timeout=15)
    d = r6.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')

    if not awb:
        # Manual Clickpost AWB creation
        print(f'  No auto-AWB, creating manually...')
        r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
        dn_data = r_dn2.json().get('data', {})
        items_list = dn_data.get('items', [])
        grand_total = max(float(dn_data.get('grand_total', 0) or 0), 1.0)
        net_total = float(dn_data.get('net_total', 0) or 0)
        total_taxes = float(dn_data.get('total_taxes_and_charges', 0) or 0)
        posting_date = dn_data.get('posting_date', '')

        for cp_id, cp_name in [(4, 'Delhivery'), (5, 'Bluedart')]:
            cp_payload = {
                'pickup_info': {
                    'pickup_name': 'WIN THE BUY BOX PVT LTD', 'pickup_phone': '9573652101',
                    'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                    'pickup_city': 'Hyderabad', 'pickup_state': 'Telangana', 'pickup_pincode': '501218',
                    'pickup_country': 'IN', 'email': 'hydwh@solara.in', 'pickup_time': '2026-05-17T10:00:00Z',
                },
                'drop_info': {
                    'drop_name': s_name, 'drop_phone': s_phone,
                    'drop_address': (s_addr1 + ' ' + s_addr2).strip(), 'drop_city': s_city,
                    'drop_state': s_state, 'drop_pincode': s_zip,
                    'drop_country': 'IN', 'drop_email': s_email,
                },
                'shipment_details': {
                    'order_type': 'PREPAID', 'invoice_value': grand_total, 'reference_number': sol,
                    'length': 30, 'breadth': 20, 'height': 15, 'weight': 500,
                    'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                               'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
                    'delivery_type': 'FORWARD', 'cod_value': 0, 'courier_partner': cp_id,
                    'invoice_number': dn_name, 'invoice_date': posting_date,
                },
                'gst_info': {
                    'seller_gstin': '36AAHCW1325Q1Z2', 'taxable_value': net_total,
                    'is_seller_registered_under_gst': True, 'place_of_supply': s_state,
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
                err = meta.get('message', '')
                print(f'    FAIL {cp_name}: {err[:200]}')
                if 'already placed' in err.lower():
                    cp_payload['shipment_details']['reference_number'] = sol + '-R1'
                    print(f'    Retrying with -R1...')
                    r_cp2 = requests.post(f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
                        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
                    meta2 = r_cp2.json().get('meta', {})
                    if meta2.get('success') and meta2.get('status') == 200:
                        awb = str(r_cp2.json().get('result', {}).get('waybill', ''))
                        courier = cp_name
                        print(f'    SUCCESS with -R1! AWB={awb} via {courier}')
                        break

        if awb:
            script = (
                f"frappe.db.set_value('Delivery Note','{dn_name}','awb_number','{awb}',update_modified=False)\n"
                f"frappe.db.set_value('Delivery Note','{dn_name}','courier_partner','{courier}',update_modified=False)\n"
                f"frappe.db.commit()\n"
                f"frappe.response['message']='ok'"
            )
            msg = run_server_script(f'tmp_awb_{sol[-4:]}', script)
            print(f'    DN AWB saved: {msg}')

    if awb:
        print(f'  AWB={awb} via {courier}')
        results.append((sol, dn_name, awb, courier))

        # Step 7: Sync to Shopify
        tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
        r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
        fos = r_fo.json().get('fulfillment_orders', [])
        open_fos = [fo for fo in fos if fo.get('status') in ('open', 'in_progress')]
        if open_fos:
            line_items_by_fo = []
            for fo in open_fos:
                fo_lines = [{'id': li['id'], 'quantity': li['fulfillable_quantity']} for li in fo.get('line_items', []) if li.get('fulfillable_quantity', 0) > 0]
                if fo_lines:
                    line_items_by_fo.append({'fulfillment_order_id': fo['id'], 'fulfillment_order_line_items': fo_lines})
            if line_items_by_fo:
                ful_payload = {
                    'fulfillment': {
                        'line_items_by_fulfillment_order': line_items_by_fo,
                        'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                        'notify_customer': True,
                    }
                }
                r_cf = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=ful_payload, timeout=30)
                print(f'  Shopify fulfillment: {r_cf.status_code}')
                if r_cf.status_code in (200, 201):
                    ful_id = r_cf.json().get('fulfillment', {}).get('id', '')
                    time.sleep(1)
                    payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': False}}
                    requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                    print(f'  Shopify 2nd push done')
        else:
            r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
            fuls = r_ful.json().get('fulfillments', [])
            if fuls:
                ful_id = str(fuls[-1].get('id', ''))
                payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
                r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
                print(f'  Shopify tracking updated: {r_u.status_code}')
    else:
        print(f'  ALL COURIERS FAILED')
        results.append((sol, dn_name, '', 'AWB_FAIL'))

print(f'\n\n{"="*60}')
print('SUMMARY')
print(f'{"="*60}')
for sol, dn, awb, courier in results:
    print(f'  {sol} | DN={dn} | AWB={awb} | {courier}')
