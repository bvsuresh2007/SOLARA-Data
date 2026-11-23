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

# Group E: Courier rejected PIN. Manual Clickpost with alternate courier.
# SOL1204408 - Anurag prasad, 744206 Andaman - Delhivery rejected. Try Bluedart (id=5)
# SOL1204568 - Anandhu pr, 686664 Kerala - PPCOD, Bluedart rejected COD. Try Delhivery (id=4) as COD

group_e = [
    ('SOL1204408', 'SHPDN27-12214', 5, 'PREPAID', 0, 'Bluedart'),       # Try Bluedart instead of Delhivery
    ('SOL1204568', 'SHPDN27-12296', 4, 'COD', 6479.19, 'Delhivery'),    # Try Delhivery instead of Bluedart for COD
]

results = []

for sol, dn, cp_id, order_type, cod_amount, courier_name in group_e:
    print(f'\n{"="*70}')
    print(f'=== {sol} | DN={dn} | Try {courier_name} | {order_type} COD={cod_amount} ===')

    # Get DN details
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H, timeout=30)
    d = r_dn.json().get('data', {})

    addr_name = d.get('shipping_address_name', '')
    r_a = requests.get(f'{BASE}/api/resource/Address/{addr_name}', headers=H, timeout=15)
    addr_data = r_a.json().get('data', {})

    drop_address = (str(addr_data.get('address_line1', '')) + ' ' + str(addr_data.get('address_line2', ''))).strip()
    items_list = d.get('items', [])
    total_weight = sum(float(it.get('total_weight', 0) or 0) for it in items_list)
    if total_weight <= 0:
        total_weight = len(items_list) * 0.5
    total_weight_g = int(total_weight * 1000) if total_weight < 50 else int(total_weight)
    if total_weight_g < 200:
        total_weight_g = 500

    grand_total = max(float(d.get('grand_total', 0) or 0), 1.0)
    phone = str(addr_data.get('phone', ''))
    if phone:
        phone = phone.replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
        if len(phone) > 10:
            phone = phone[-10:]

    pin = str(addr_data.get('pincode', ''))
    print(f'  Customer: {d.get("customer_name","")} | PIN: {pin}')
    print(f'  Grand Total: {grand_total} | Weight: {total_weight_g}g')

    cp_payload = {
        'pickup_info': {
            'pickup_name': 'WIN THE BUY BOX PVT LTD',
            'pickup_phone': '9573652101',
            'pickup_address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
            'pickup_city': 'Hyderabad',
            'pickup_state': 'Telangana',
            'pickup_pincode': '501218',
            'pickup_country': 'IN',
            'email': 'hydwh@solara.in',
            'pickup_time': '2026-05-08T10:00:00Z',
        },
        'drop_info': {
            'drop_name': d.get('customer_name', ''),
            'drop_phone': phone,
            'drop_address': drop_address,
            'drop_city': addr_data.get('city', ''),
            'drop_state': addr_data.get('state', ''),
            'drop_pincode': pin,
            'drop_country': 'IN',
            'drop_email': addr_data.get('email_id', '') or 'noreply@solara.in',
        },
        'shipment_details': {
            'order_type': order_type,
            'invoice_value': grand_total,
            'reference_number': sol,
            'length': 30, 'breadth': 20, 'height': 15,
            'weight': total_weight_g,
            'items': [{'sku': it.get('item_code',''), 'description': str(it.get('item_name',''))[:100],
                       'quantity': int(it.get('qty',1)), 'price': float(it.get('rate',0) or 0)} for it in items_list],
            'delivery_type': 'FORWARD',
            'cod_value': cod_amount,
            'courier_partner': cp_id,
            'invoice_number': dn,
            'invoice_date': d.get('posting_date', ''),
        },
        'gst_info': {
            'seller_gstin': '36AAHCW1325Q1Z2',
            'taxable_value': float(d.get('net_total', 0) or 0),
            'ewaybill_serial_number': '',
            'is_seller_registered_under_gst': True,
            'place_of_supply': addr_data.get('state', ''),
            'cstin': '',
            'sgst_tax_rate': 0, 'cgst_tax_rate': 0, 'igst_tax_rate': 18,
            'sgst_amount': 0, 'cgst_amount': 0,
            'igst_amount': float(d.get('total_taxes_and_charges', 0) or 0),
            'invoice_number': dn, 'invoice_date': d.get('posting_date', ''), 'hsn_code': '',
        },
        'additional': {
            'label': True,
            'return_info': {
                'name': 'WIN THE BUY BOX PVT LTD',
                'phone': '9573652101',
                'address': 'SY NO.68/1/E, Hamedullah Nagar Village, Shamshabad Mandal, Ranga Reddy District',
                'city': 'Hyderabad',
                'state': 'Telangana',
                'pincode': '501218',
                'country': 'IN',
            },
            'async': False,
        },
    }

    r_cp = requests.post(
        f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
        json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)

    cp_resp = r_cp.json()
    meta = cp_resp.get('meta', {})

    if meta.get('success') and meta.get('status') == 200:
        awb = str(cp_resp.get('result', {}).get('waybill', ''))
        print(f'  AWB={awb} {courier_name}')

        # Save AWB to DN
        sn = 'tmp_awb_' + dn.replace('-', '_').lower()
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
        time.sleep(1)
        script = (
            "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + awb + "',update_modified=False)\n"
            "frappe.db.set_value('Delivery Note','" + dn + "','courier_partner','" + courier_name + "',update_modified=False)\n"
            "frappe.db.commit()\n"
            "frappe.response['message']='ok'"
        )
        r_ts = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
            json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
        if r_ts.status_code == 200:
            requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
            time.sleep(3)
            requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
            requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
            print(f'  AWB saved to DN')

        # Sync to Shopify
        shopify_oid = d.get('shopify_order_id', '')
        if shopify_oid:
            tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'

            r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json',
                                headers=SHOP_H, timeout=15)
            fos = r_fo.json().get('fulfillment_orders', [])
            open_fos = []
            for fo in fos:
                if fo.get('status') in ('open', 'in_progress'):
                    fo_items = []
                    for li in fo.get('line_items', []):
                        fq = li.get('fulfillable_quantity', 0)
                        if fq > 0:
                            fo_items.append({'id': li['id'], 'quantity': fq})
                    if fo_items:
                        open_fos.append({
                            'fulfillment_order_id': fo['id'],
                            'fulfillment_order_line_items': fo_items
                        })

            if open_fos:
                payload = {
                    'fulfillment': {
                        'line_items_by_fulfillment_order': open_fos,
                        'tracking_info': {
                            'number': awb,
                            'url': tracking_url,
                            'company': courier_name,
                        },
                        'notify_customer': True,
                    }
                }
                r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json',
                                    headers=SHOP_H, json=payload, timeout=30)
                if r_f.status_code in (200, 201):
                    sf_id = r_f.json().get('fulfillment', {}).get('id', '')
                    print(f'  Shopify fulfillment: {sf_id}')
                    # Save fulfillment_id
                    sn2 = 'tmp_sfid_' + dn.replace('-', '_').lower()
                    requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)
                    time.sleep(1)
                    script2 = (
                        "frappe.db.set_value('Delivery Note','" + dn + "','shopify_fulfillment_id','" + str(sf_id) + "',update_modified=False)\n"
                        "frappe.db.commit()\n"
                        "frappe.response['message']='ok'"
                    )
                    r_ts2 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
                        json={'name': sn2, 'script_type': 'API', 'api_method': sn2, 'script': script2, 'allow_guest': 0}, timeout=15)
                    if r_ts2.status_code == 200:
                        requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
                        time.sleep(3)
                        requests.get(f'{BASE}/api/method/{sn2}', headers=H, timeout=15)
                        requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)
                else:
                    print(f'  Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:200]}')
            else:
                r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json',
                                     headers=SHOP_H, timeout=15)
                existing = r_ful.json().get('fulfillments', [])
                if existing:
                    ful_id = str(existing[-1].get('id', ''))
                    payload = {
                        'fulfillment': {
                            'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier_name},
                            'notify_customer': True,
                        }
                    }
                    r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                                        headers=SHOP_H, json=payload, timeout=15)
                    if r_u.status_code in (200, 201):
                        print(f'  Shopify tracking updated on {ful_id}')
                    else:
                        print(f'  Shopify tracking update FAIL: {r_u.status_code}')
                else:
                    print(f'  No open FOs or existing fulfillments')

        results.append((sol, 'OK', dn, awb, courier_name))
    else:
        err_msg = meta.get('message', '')
        print(f'  CLICKPOST FAIL: {err_msg}')
        print(f'  Full response: {json.dumps(cp_resp)[:400]}')

        # If first courier failed, try the other one
        alt_cp_id = 4 if cp_id == 5 else 5
        alt_name = 'Delhivery' if alt_cp_id == 4 else 'Bluedart'
        print(f'\n  Retrying with {alt_name} (id={alt_cp_id})...')
        cp_payload['shipment_details']['courier_partner'] = alt_cp_id

        r_cp2 = requests.post(
            f'https://www.clickpost.in/api/v3/create-order/?username=solara&key={CP_KEY}',
            json=cp_payload, headers={'Content-Type': 'application/json'}, timeout=30)
        cp_resp2 = r_cp2.json()
        meta2 = cp_resp2.get('meta', {})

        if meta2.get('success') and meta2.get('status') == 200:
            awb = str(cp_resp2.get('result', {}).get('waybill', ''))
            print(f'  AWB={awb} {alt_name}')
            results.append((sol, 'OK_ALT', dn, awb, alt_name))

            # Save AWB
            sn = 'tmp_awb2_' + dn.replace('-', '_').lower()
            requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
            time.sleep(1)
            script = (
                "frappe.db.set_value('Delivery Note','" + dn + "','awb_number','" + awb + "',update_modified=False)\n"
                "frappe.db.set_value('Delivery Note','" + dn + "','courier_partner','" + alt_name + "',update_modified=False)\n"
                "frappe.db.commit()\n"
                "frappe.response['message']='ok'"
            )
            r_ts = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
                json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
            if r_ts.status_code == 200:
                requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
                time.sleep(3)
                requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
                requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
                print(f'  AWB saved to DN')

            # Shopify sync
            shopify_oid = d.get('shopify_order_id', '')
            if shopify_oid:
                tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'
                r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json',
                                    headers=SHOP_H, timeout=15)
                fos = r_fo.json().get('fulfillment_orders', [])
                open_fos = []
                for fo in fos:
                    if fo.get('status') in ('open', 'in_progress'):
                        fo_items = []
                        for li in fo.get('line_items', []):
                            fq = li.get('fulfillable_quantity', 0)
                            if fq > 0:
                                fo_items.append({'id': li['id'], 'quantity': fq})
                        if fo_items:
                            open_fos.append({
                                'fulfillment_order_id': fo['id'],
                                'fulfillment_order_line_items': fo_items
                            })
                if open_fos:
                    payload = {
                        'fulfillment': {
                            'line_items_by_fulfillment_order': open_fos,
                            'tracking_info': {'number': awb, 'url': tracking_url, 'company': alt_name},
                            'notify_customer': True,
                        }
                    }
                    r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json',
                                        headers=SHOP_H, json=payload, timeout=30)
                    if r_f.status_code in (200, 201):
                        sf_id = r_f.json().get('fulfillment', {}).get('id', '')
                        print(f'  Shopify fulfillment: {sf_id}')
                    else:
                        print(f'  Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:200]}')
                else:
                    print(f'  No open FOs for Shopify sync')
        else:
            err_msg2 = meta2.get('message', '')
            print(f'  ALT ALSO FAILED: {err_msg2}')
            print(f'  Full: {json.dumps(cp_resp2)[:300]}')
            results.append((sol, 'FAIL_BOTH', dn, err_msg[:80], err_msg2[:80]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP E SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] in ('OK', 'OK_ALT'):
        print(f'  {r[0]}: {r[1]} {r[2]} AWB={r[3]} {r[4]}')
    else:
        print(f'  {r[0]}: {r[1]} {" ".join(str(x) for x in r[2:])}')
