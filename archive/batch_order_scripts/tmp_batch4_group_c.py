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

# Group C: Draft DN, serviceable, no issues - just submit
orders = [
    'SOL1204751',  # Siddharth Patnaik, 562125 Bangalore, Prepaid
    'SOL1205004',  # Lakshmi Sarkar, 713213 WB, Prepaid
    'SOL1205008',  # Dhaval prajapati, 388325 Gujarat, Prepaid
    'SOL1205037',  # Tisha Rita, 400064 Mumbai, PPCOD
    'SOL1205090',  # Harsh, 201013 Ghaziabad, Prepaid
]

results = []

for sol in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} ===')

    # Find draft DN
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol],['docstatus','=',0]]),
                'fields': json.dumps(['name','customer_name','grand_total','shipping_address_name',
                                      'shopify_order_id','shopify_order_number']),
                'limit_page_length': 5}, timeout=15)
    dns = r_dn.json().get('data', [])

    if not dns:
        print(f'  No draft DN found!')
        results.append((sol, 'FAIL', '', '', 'No draft DN'))
        continue

    dn = dns[0]
    dn_name = dn['name']
    print(f'  DN: {dn_name} | {dn.get("customer_name","")} | Total={dn.get("grand_total",0)}')
    print(f'  Ship addr: {dn.get("shipping_address_name","")} | Shopify ID: {dn.get("shopify_order_id","")}')

    # Verify DN has shopify_order_id (needed for Clickpost trigger)
    if not dn.get('shopify_order_id'):
        # Get from SO
        r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['shopify_order_id']),
                    'limit_page_length': 1}, timeout=15)
        so_data = r_so.json().get('data', [])
        if so_data and so_data[0].get('shopify_order_id'):
            sid = so_data[0]['shopify_order_id']
            print(f'  Setting shopify_order_id={sid} on DN...')
            requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',
                headers=H, json={'shopify_order_id': sid, 'shopify_order_number': sol}, timeout=15)
            time.sleep(0.5)

    # Verify shipping_address_name exists
    if not dn.get('shipping_address_name'):
        r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['shipping_address_name','customer_address']),
                    'limit_page_length': 1}, timeout=15)
        so_data = r_so.json().get('data', [])
        if so_data and so_data[0].get('shipping_address_name'):
            sa = so_data[0]['shipping_address_name']
            ca = so_data[0].get('customer_address', sa)
            print(f'  Setting shipping_address_name={sa} on DN...')
            requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',
                headers=H, json={'shipping_address_name': sa, 'customer_address': ca}, timeout=15)
            time.sleep(0.5)

    # Submit
    print(f'  Submitting DN {dn_name}...')
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',
        headers=H, json={'docstatus': 1}, timeout=60)

    if r_sub.status_code == 200:
        dn_data = r_sub.json().get('data', {})
        awb = dn_data.get('awb_number', '') or ''
        courier = dn_data.get('courier_partner', '') or ''
        print(f'  ✓ Submitted | AWB={awb} | Courier={courier}')

        if not awb:
            time.sleep(3)
            r_check = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
                params={'fields': json.dumps(['awb_number','courier_partner'])}, timeout=15)
            d2 = r_check.json().get('data', {})
            awb = d2.get('awb_number', '') or ''
            courier = d2.get('courier_partner', '') or ''
            if awb:
                print(f'  ✓ AWB (delayed): {awb} via {courier}')
            else:
                print(f'  ⚠ No AWB - may need manual Clickpost')

        # Verify Shopify fulfillment
        shopify_oid = dn.get('shopify_order_id', '')
        if not shopify_oid:
            r_so2 = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
                params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                        'fields': json.dumps(['shopify_order_id']),
                        'limit_page_length': 1}, timeout=15)
            so2 = r_so2.json().get('data', [])
            if so2:
                shopify_oid = so2[0].get('shopify_order_id', '')

        if shopify_oid and awb:
            time.sleep(1)
            r_ord = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H, timeout=15)
            sh = r_ord.json().get('order', {})
            ful_status = sh.get('fulfillment_status', '')
            fin = sh.get('financial_status', '')
            gw = ', '.join(sh.get('payment_gateway_names', []))
            print(f'  Shopify: fin={fin} | fulfillment={ful_status} | gw={gw}')

        results.append((sol, 'OK', dn_name, awb, courier))
    else:
        err = r_sub.text[:300]
        print(f'  ✗ Submit FAIL: {r_sub.status_code} {err}')
        results.append((sol, 'FAIL', dn_name, '', err[:100]))

    time.sleep(1)

print(f'\n\n{"="*70}')
print('GROUP C SUMMARY')
print(f'{"="*70}')
for r in results:
    if r[1] == 'OK':
        print(f'  ✓ {r[0]}: DN={r[2]} | AWB={r[3]} | {r[4]}')
    else:
        print(f'  ✗ {r[0]}: {r[4]}')
