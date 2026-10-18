import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

r2 = requests.post(f'{BASE}/api/method/frappe.client.get_password',
    headers=H, json={'doctype': 'Shopify Setting', 'name': 'Shopify Setting', 'fieldname': 'password'}, timeout=30)
token = r2.json().get('message', '')
SHOP = 'https://dev-solara.myshopify.com'
SHOP_H = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

sol = 'SOL1197271'
dn = 'SHPDN27-03742'
awb = '29044411116920'
courier = 'Delhivery'

# Get shopify_order_id from DN
r_dn = requests.get(f'{BASE}/api/resource/Delivery Note/{dn}', headers=H,
    params={'fields': json.dumps(['shopify_order_id','shopify_fulfillment_id'])}, timeout=15)
dd = r_dn.json().get('data', {})
shopify_oid = dd.get('shopify_order_id', '')
existing_ful = dd.get('shopify_fulfillment_id', '') or ''
print(f'DN: {dn} | OID={shopify_oid} | existing_ful={existing_ful}')

if not shopify_oid:
    # Get from SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['shopify_order_id']),
                'limit_page_length': 1}, timeout=15)
    sos = r_so.json().get('data', [])
    if sos:
        shopify_oid = sos[0].get('shopify_order_id', '')
        print(f'Got OID from SO: {shopify_oid}')

if not shopify_oid:
    print('No shopify_order_id found!')
    exit()

tracking_url = f'https://www.clickpost.in/tracking/#/{awb}'

# Check current Shopify fulfillment status
r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
sh_ord = r_ord.json().get('order', {})
print(f'Shopify: fulfillment_status={sh_ord.get("fulfillment_status","")} | fin={sh_ord.get("financial_status","")}')

# Get fulfillment orders
r_fo = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillment_orders.json',
                    headers=SHOP_H, timeout=15)
fos = r_fo.json().get('fulfillment_orders', [])
open_fos = []
for fo in fos:
    print(f'  FO {fo["id"]}: status={fo.get("status","")}')
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
                'company': courier,
            },
            'notify_customer': True,
        }
    }
    r_f = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments.json',
                        headers=SHOP_H, json=payload, timeout=30)
    if r_f.status_code in (200, 201):
        sf_id = r_f.json().get('fulfillment', {}).get('id', '')
        print(f'Shopify fulfillment created: {sf_id}')

        # Save to DN
        sn = 'tmp_sfid_3742'
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
        time.sleep(1)
        script = (
            "frappe.db.set_value('Delivery Note','" + dn + "','shopify_fulfillment_id','" + str(sf_id) + "',update_modified=False)\n"
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
            print(f'Fulfillment ID saved to DN')
    else:
        print(f'Shopify fulfillment FAIL: {r_f.status_code} {r_f.text[:300]}')
else:
    # Check existing fulfillments - maybe already fulfilled, update tracking
    r_ful = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}/fulfillments.json',
                         headers=SHOP_H, timeout=15)
    existing = r_ful.json().get('fulfillments', [])
    if existing:
        ful_id = str(existing[-1].get('id', ''))
        cur_tracking = existing[-1].get('tracking_number', '')
        print(f'Existing fulfillment {ful_id} tracking={cur_tracking}')
        if cur_tracking == awb:
            print(f'Already synced with correct AWB!')
        else:
            payload = {
                'fulfillment': {
                    'tracking_info': {'number': awb, 'url': tracking_url, 'company': courier},
                    'notify_customer': True,
                }
            }
            r_u = requests.post(f'{SHOP}/admin/api/2024-01/fulfillments/{ful_id}/update_tracking.json',
                                headers=SHOP_H, json=payload, timeout=15)
            if r_u.status_code in (200, 201):
                print(f'Shopify tracking updated on {ful_id}')
            else:
                print(f'Shopify tracking update FAIL: {r_u.status_code} {r_u.text[:200]}')
    else:
        print(f'No open FOs and no existing fulfillments!')
