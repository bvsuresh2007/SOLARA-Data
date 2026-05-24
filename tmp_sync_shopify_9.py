import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password', headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': r2.json().get('message',''), 'Content-Type': 'application/json'}

orders = [
    # (sol, so_name, awb, courier) - skip SOL1202753 already synced
    ('SOL1205358', 'SHP27-11655', '29044411231263', 'Delhivery'),
    ('SOL1200450', 'SHP27-06613', '29044411231274', 'Delhivery'),  # update_tracking
    ('SOL1202432', 'SHP27-08679', '29044411231285', 'Delhivery'),
    ('SOL1202791', 'SHP27-09090', '29044411231311', 'Delhivery'),
    ('SOL1202422', 'SHP27-08669', '29044411231296', 'Delhivery'),
    ('SOL1197981', 'SHP27-04151', '50938654955', 'Bluedart'),
    ('SOL1206214', 'SHP27-12514', '50938654966', 'Bluedart'),
    ('SOL1205979', 'SHP27-12283', '29044411231300', 'Delhivery'),
]

results = []

for sol, so_name, awb, courier in orders:
    print(f'\n{"="*60}')
    print(f'=== {sol} ===')

    # Get shopify_order_id
    r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, params={
        'fields': json.dumps(['shopify_order_id'])
    }, timeout=15)
    shopify_oid = r.json().get('data', {}).get('shopify_order_id', '')
    if not shopify_oid:
        print(f'  NO shopify_order_id!')
        results.append((sol, 'NO_OID'))
        continue

    tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'

    # Check existing fulfillments
    r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json', headers=SHOP_H, timeout=15)
    fuls = r_ful.json().get('fulfillments', [])

    if fuls:
        # Update tracking on existing fulfillment
        ful_id = str(fuls[-1].get('id', ''))
        payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': True}}
        r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
        print(f'  Updated tracking on fulfillment {ful_id}: {r_u.status_code}')
        time.sleep(1)
        r_u2 = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
        print(f'  2nd push: {r_u2.status_code}')
        results.append((sol, 'UPDATED'))
    else:
        # Create new fulfillment via fulfillment_orders API
        r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json', headers=SHOP_H, timeout=15)
        fos = r_fo.json().get('fulfillment_orders', [])
        open_fos = [fo for fo in fos if fo.get('status') in ('open', 'in_progress')]

        if not open_fos:
            print(f'  No open fulfillment orders! Statuses: {[fo.get("status") for fo in fos]}')
            results.append((sol, 'NO_OPEN_FO'))
            continue

        # Build fulfillment payload with all open FOs
        line_items_by_fo = []
        for fo in open_fos:
            fo_line_items = []
            for li in fo.get('line_items', []):
                fo_line_items.append({'id': li['id'], 'quantity': li['fulfillable_quantity']})
            if fo_line_items:
                line_items_by_fo.append({
                    'fulfillment_order_id': fo['id'],
                    'fulfillment_order_line_items': fo_line_items
                })

        if not line_items_by_fo:
            print(f'  No fulfillable line items!')
            results.append((sol, 'NO_ITEMS'))
            continue

        ful_payload = {
            'fulfillment': {
                'line_items_by_fulfillment_order': line_items_by_fo,
                'tracking_info': {
                    'number': awb,
                    'url': tracking_url,
                    'company': courier,
                },
                'notify_customer': True,
            }
        }

        r_cf = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json', headers=SHOP_H, json=ful_payload, timeout=30)
        if r_cf.status_code in (200, 201):
            ful_id = r_cf.json().get('fulfillment', {}).get('id', '')
            print(f'  Fulfillment created! ID={ful_id}')
            # Double push tracking
            time.sleep(1)
            payload = {'fulfillment': {'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier}, 'notify_customer': False}}
            r_u2 = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json', headers=SHOP_H, json=payload, timeout=15)
            print(f'  2nd tracking push: {r_u2.status_code}')
            results.append((sol, 'CREATED'))
        else:
            err = r_cf.text[:300]
            print(f'  Fulfillment create failed: {r_cf.status_code} {err}')
            results.append((sol, 'FAIL'))

    time.sleep(0.5)

print(f'\n\n{"="*80}')
print('SUMMARY')
print(f'{"="*80}')
for sol, status in results:
    print(f'  {sol} | {status}')
