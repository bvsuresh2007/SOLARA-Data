import os, requests, json, sys, time
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
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200:
        print(f'  Script create failed: {r.status_code} {r.text[:200]}')
        return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(5)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=10)
    if exc:
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

orders = [
    'SOL1205358', 'SOL1200450', 'SOL1202432', 'SOL1202791', 'SOL1202422',
    'SOL1202753', 'SOL1197981', 'SOL1206214', 'SOL1205979',
]

results = []

for sol in orders:
    print(f'\n{"="*70}')
    print(f'=== {sol} ===')

    # 1. Get SO
    r = requests.get(f'{BASE}/api/resource/Sales Order', headers=H, params={
        'filters': json.dumps([['shopify_order_number','=',sol]]),
        'fields': json.dumps(['name','customer','grand_total','docstatus','custom_order_type',
                              'shipping_address_name','customer_address','taxes_and_charges',
                              'shopify_order_id','custom_cod_amount'])
    }, timeout=15)
    sos = r.json().get('data', [])
    if not sos:
        print(f'  NO SO FOUND')
        results.append((sol, 'NO_SO', '', '', ''))
        continue
    so = sos[0]
    so_name = so['name']
    cust = so.get('customer', '')
    otype = so.get('custom_order_type', 'Prepaid')
    shopify_oid = so.get('shopify_order_id', '')
    cod_amount = float(so.get('custom_cod_amount', 0) or 0)
    taxes = so.get('taxes_and_charges', '')
    print(f'  SO={so_name} | {cust} | {otype} | COD={cod_amount}')

    if not shopify_oid:
        print(f'  NO shopify_order_id!')
        results.append((sol, 'NO_SHOPIFY_OID', so_name, '', cust))
        continue

    # 2. Get Shopify shipping address
    rs = requests.get(f'{SHOP}/admin/api/2024-01/orders/{shopify_oid}.json', headers=SHOP_H,
                      params={'fields': 'id,name,shipping_address'}, timeout=30)
    shop_data = rs.json().get('order', {})
    sa = shop_data.get('shipping_address', {})
    s_name = sa.get('name', '')
    s_first = sa.get('first_name', '')
    s_last = sa.get('last_name', '')
    s_addr1 = sa.get('address1', '')
    s_addr2 = sa.get('address2', '')
    s_city = sa.get('city', '')
    s_state = sa.get('province', '')
    s_zip = str(sa.get('zip', '')).strip()
    s_phone = str(sa.get('phone', '')).replace('+91','').replace('+','').replace(' ','').replace('-','').strip()
    if len(s_phone) > 10: s_phone = s_phone[-10:]
    s_country = sa.get('country_code', 'IN')
    print(f'  Shopify: {s_name} | {s_addr1}, {s_addr2} | {s_city}, {s_state} {s_zip} | Ph: {s_phone}')

    # 3. Create/update Address on Atlas: {customer}-{sol}-Shipping
    addr_name = f'{cust}-{sol}-Shipping'
    # Check if exists
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
        'email_id': sa.get('email', '') or 'noreply@solara.in',
        'is_shipping_address': 1,
        'links': [{'link_doctype': 'Customer', 'link_name': cust}],
    }
    if r_ae.status_code == 200:
        # Update existing
        r_au = requests.put(f'{BASE}/api/resource/Address/{addr_name}', headers=H, json=addr_payload, timeout=15)
        if r_au.status_code == 200:
            print(f'  Address updated: {addr_name}')
        else:
            print(f'  Address update failed: {r_au.status_code} {r_au.text[:200]}')
    else:
        # Create new
        addr_payload['name'] = addr_name
        r_ac = requests.post(f'{BASE}/api/resource/Address', headers=H, json=addr_payload, timeout=15)
        if r_ac.status_code == 200:
            addr_name = r_ac.json().get('data', {}).get('name', addr_name)
            print(f'  Address created: {addr_name}')
        else:
            print(f'  Address create failed: {r_ac.status_code} {r_ac.text[:200]}')
            results.append((sol, 'ADDR_FAIL', so_name, '', cust))
            continue

    # 4. Update SO shipping_address_name + customer_address via server script
    sn = f'tmp_addr_{sol.lower()}'
    script = (
        f"frappe.db.set_value('Sales Order','{so_name}','shipping_address_name','{addr_name}',update_modified=False)\n"
        f"frappe.db.set_value('Sales Order','{so_name}','customer_address','{addr_name}',update_modified=False)\n"
        f"frappe.db.commit()\n"
        f"frappe.response['message']='ok'"
    )
    msg = run_server_script(sn, script)
    print(f'  SO address updated: {msg}')

    # 5. Create DN from SO
    r_dn = requests.get(f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
        headers=H, params={'source_name': so_name}, timeout=15)
    if r_dn.status_code != 200:
        print(f'  make_delivery_note failed: {r_dn.status_code} {r_dn.text[:200]}')
        results.append((sol, 'MAKE_DN_FAIL', so_name, '', cust))
        continue

    dn_draft = r_dn.json().get('message', {})
    dn_draft['shipping_address_name'] = addr_name
    dn_draft['customer_address'] = addr_name
    dn_draft['taxes'] = []
    dn_draft['taxes_and_charges'] = taxes
    for item in dn_draft.get('items', []):
        item.pop('item_tax_template', None)
    for key in ['__islocal', '__unsaved', 'amended_from']:
        dn_draft.pop(key, None)

    # Save DN
    r_ds = requests.post(f'{BASE}/api/resource/Delivery Note', headers=H, json=dn_draft, timeout=30)
    if r_ds.status_code != 200:
        print(f'  DN save failed: {r_ds.status_code} {r_ds.text[:300]}')
        results.append((sol, 'DN_SAVE_FAIL', so_name, '', cust))
        continue

    dn_name = r_ds.json().get('data', {}).get('name', '')
    print(f'  DN created: {dn_name}')

    # 6. Submit DN
    r_sub = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, json={'docstatus': 1}, timeout=30)
    if r_sub.status_code == 200:
        print(f'  DN submitted!')
    elif r_sub.status_code == 417:
        time.sleep(2)
        r_chk = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H,
            params={'fields': json.dumps(['docstatus'])}, timeout=15)
        if r_chk.json().get('data', {}).get('docstatus') == 1:
            print(f'  DN submitted (417 OK)!')
        else:
            err = r_sub.text[:300]
            print(f'  DN submit failed: {err}')
            if 'NegativeStockError' in err:
                results.append((sol, 'NO_STOCK', so_name, dn_name, cust))
            else:
                results.append((sol, 'DN_SUBMIT_FAIL', so_name, dn_name, cust))
            continue
    else:
        err = r_sub.text[:300]
        print(f'  DN submit failed: {r_sub.status_code} {err}')
        if 'NegativeStockError' in err:
            results.append((sol, 'NO_STOCK', so_name, dn_name, cust))
        else:
            results.append((sol, 'DN_SUBMIT_FAIL', so_name, dn_name, cust))
        continue

    # 7. Check AWB (Clickpost auto-fires on DN submit)
    time.sleep(3)
    r_awb = requests.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, params={
        'fields': json.dumps(['awb_number', 'courier_partner', 'docstatus'])
    }, timeout=15)
    d = r_awb.json().get('data', {})
    awb = d.get('awb_number', '')
    courier = d.get('courier_partner', '')
    print(f'  AWB={awb} | {courier}')
    results.append((sol, 'OK', so_name, dn_name, cust, f'{awb} ({courier})'))
    time.sleep(0.5)

print(f'\n\n{"="*80}')
print(f'SUMMARY')
print(f'{"="*80}')
ok = [r for r in results if r[1] == 'OK']
fail = [r for r in results if r[1] != 'OK']
for r in ok:
    print(f'  OK       {r[0]} | {r[4]} | {r[2]} | {r[3]} | {r[5]}')
for r in fail:
    dn_info = r[3] if len(r) > 3 else ''
    cust_info = r[4] if len(r) > 4 else ''
    print(f'  {r[1]:15s} {r[0]} | {cust_info} | {r[2]} | {dn_info}')
print(f'\n  Total: {len(ok)} OK | {len(fail)} failed')
