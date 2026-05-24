import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r = requests.post(f'{BASE}/api/method/frappe.client.get_password',
                   headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

# All orders needing Shopify fulfillment sync
to_sync = [
    ('SOL1202824', 'SHPDN27-10780', '50938446974', 'Bluedart'),
    ('SOL1202897', 'SHPDN27-10831', '50938446985', 'Bluedart'),
    ('SOL1202978', 'SHPDN27-10765', '50938447324', 'Bluedart'),
    ('SOL1202968', 'SHPDN27-11250', '68509725373', 'Bluedart'),
    ('SOL1202828', 'SHPDN27-11249', '29044411190814', 'Delhivery'),  # PPCOD recreated
]

results = []
for sol, dn, awb, courier in to_sync:
    print(f"\n=== {sol} {dn} AWB={awb} ===")

    # Get Shopify order ID from SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',1]]),
                'fields': json.dumps(['name','shopify_order_id']),
                'limit_page_length': 1}, timeout=20)
    sos = r_so.json().get('data', [])
    if not sos or not sos[0].get('shopify_order_id'):
        print(f"  No Shopify order ID found")
        results.append((sol, 'NO_OID'))
        continue

    oid = sos[0]['shopify_order_id']
    tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'

    # Check existing fulfillments
    r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}/fulfillments.json', headers=SHOP_H, timeout=15)
    existing = r_ful.json().get('fulfillments', [])

    # Get fulfillment orders
    r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
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
        # Create new fulfillment
        payload = {
            'fulfillment': {
                'line_items_by_fulfillment_order': open_fos,
                'tracking_info': {
                    'number': awb,
                    'url': tracking_url,
                    'company': courier,
                },
                'notify_customer': True,
            }
        }
        r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json',
                            headers=SHOP_H, json=payload, timeout=30)
        if r_f.status_code in (200, 201):
            sf_id = r_f.json().get('fulfillment', {}).get('id', '')
            print(f"  Fulfillment created: {sf_id}")

            # Save fulfillment_id to DN
            sn = 'tmp_sfid_' + dn.replace('-', '_').lower()
            script = (
                "frappe.db.set_value('Delivery Note','" + dn + "','shopify_fulfillment_id','" + str(sf_id) + "',update_modified=False)\n"
                "frappe.db.commit()\n"
                "frappe.response['message']='ok'"
            )
            r_ts = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
                json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
            if r_ts.status_code == 200:
                requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
                requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)

            results.append((sol, 'OK_NEW', sf_id))
        else:
            print(f"  Fulfillment FAIL: {r_f.status_code} {r_f.text[:200]}")
            results.append((sol, 'FAIL_NEW', r_f.text[:80]))
    elif existing:
        # Update tracking on existing fulfillment
        ful_id = str(existing[-1].get('id', ''))
        payload = {
            'fulfillment': {
                'tracking_info': {
                    'number': awb,
                    'url': tracking_url,
                    'company': courier,
                },
                'notify_customer': True,
            }
        }
        r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                            headers=SHOP_H, json=payload, timeout=15)
        if r_u.status_code in (200, 201):
            print(f"  Tracking updated on fulfillment {ful_id}")
            results.append((sol, 'OK_UPD', ful_id))
        else:
            print(f"  Tracking update FAIL: {r_u.status_code} {r_u.text[:200]}")
            results.append((sol, 'FAIL_UPD', r_u.text[:80]))
    else:
        print(f"  No open FOs and no existing fulfillments")
        results.append((sol, 'NO_FO'))

    time.sleep(1)

print(f"\n{'='*70}")
print(f"SUMMARY")
for r in results:
    print(f"  {r[0]}: {r[1]} {r[2] if len(r) > 2 else ''}")
