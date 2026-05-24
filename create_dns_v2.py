import requests, json, time
from dotenv import dotenv_values

env = dotenv_values('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
s = requests.Session()
s.headers.update({
    'Authorization': f'token {env["ERPNEXT_API_KEY"]}:{env["ERPNEXT_API_SECRET"]}',
    'Content-Type': 'application/json'
})
BASE = env['ERPNEXT_URL']

# Get Shopify creds
r0 = s.get(f'{BASE}/api/resource/Shopify Setting/Shopify Setting', timeout=15)
sdata = r0.json()['data']
shop_url = sdata['shopify_url']
shop_token = sdata['password']
shopify_s = requests.Session()
shopify_s.headers.update({'X-Shopify-Access-Token': shop_token, 'Content-Type': 'application/json'})

order_map = {
    'SOL1193560': ('SHP-2026-2027-00139-1', None),
    'SOL1193617': ('SHP-2026-2027-00081-1', None),
    'SOL1193623': ('SHP-2026-2027-00087-1', None),
    'SOL1193679': ('SHP-2026-2027-00183-1', None),
    'SOL1193720': ('SHP-2026-2027-00217-1', None),
    'SOL1193745': ('SHP-2026-2027-00238-1', None),
    'SOL1193820': ('SHP-2026-2027-00306-1', None),
    'SOL1193874': ('SHP-2026-2027-00354-1', None),
    'SOL1193935': ('SHP27-00007-1', None),
    'SOL1193941': ('SHP27-00013-1', None),
    'SOL1193976': ('SHP27-00045-1', None),
    'SOL1194016': ('SHP27-00084-1', None),
    'SOL1194030': ('SHP27-00098-1', None),
    'SOL1193532': ('SHP-2026-2027-00112', 'SHPDN27-00048'),
    'SOL1193572': ('SHP-2026-2027-00035', 'SHPDN27-00322'),
    'SOL1193513': ('SHP-2026-2027-00019', 'SHPDN-2026-2027-00108'),
    'SOL1193772': ('SHP-2026-2027-00261', 'SHPDN-2026-2027-00032'),
    'SOL1193641': ('SHP27-00149-1', None),
    'SOL1194231': ('SHP27-00357-1', 'SHPDN27-00810'),
    'SOL1194240': ('SHP27-00366-1', 'SHPDN27-00809'),
    'SOL1193914': ('SHP-2026-2027-00389', 'SHPDN27-00147'),
    'SOL1193528': ('SHP-2026-2027-00108', 'SHPDN27-00047'),
    'SOL1194106': ('SHP27-00232-1', 'SHPDN27-00819'),
    'SOL1194275': ('SHP27-00400', 'SHPDN27-00693'),
    'SOL1193754': ('SHP27-00133', 'SHPDN27-00272'),
    'SOL1193889': ('SHP27-00122', 'SHPDN27-00405'),
    'SOL1193678': ('SHP-2026-2027-00182-1', None),
    'SOL1193516': ('SHP-2026-2027-00021-1', 'SHPDN27-00319'),
    'SOL1193505': ('SHP-2026-2027-00011', 'SHPDN27-00020'),
    'SOL1193498': ('SHP-2026-2027-00005', 'SHPDN27-00315'),
    'SOL1193839': ('SHP27-00127', 'SHPDN27-00266'),
    'SOL1193787': ('SHP-2026-2027-00274', 'SHPDN27-00018'),
    'SOL1193795': ('SHP27-00129', 'SHPDN27-00407'),
    'SOL1193978': ('SHP27-00047', 'SHPDN27-00195'),
    'SOL1193642': ('SHP27-00148', 'SHPDN27-00413'),
    'SOL1194057': ('SHP27-00181-1', 'SHPDN27-00820'),
    'SOL1194052': ('SHP27-00176-1', 'SHPDN27-00821'),
    'SOL1193726': ('SHP27-00137', 'SHPDN27-00276'),
    'SOL1193891': ('SHP27-00121', 'SHPDN27-00260'),
    'SOL1193894': ('SHP27-00120', 'SHPDN27-00403'),
    'SOL1193684': ('SHP27-00141', 'SHPDN27-00280'),
    'SOL1194140': ('SHP27-00266-1', 'SHPDN27-00816'),
    'SOL1193683': ('SHP-2026-2027-00186', 'SHPDN27-00063'),
    'SOL1194280': ('SHP27-00404-1', 'SHPDN27-00805'),
    'SOL1194113': ('SHP27-00239', 'SHPDN27-00463'),
    'SOL1193556': ('SHP-2026-2027-00135', 'SHPDN-2026-2027-00206'),
}

order_list = list(order_map.keys())
results = []


def get_shopify_order_id(oid):
    r = shopify_s.get(f'https://{shop_url}/admin/api/2024-01/orders.json', params={
        'name': oid, 'status': 'any', 'limit': 5
    }, timeout=15)
    orders = r.json().get('orders', [])
    return str(orders[0]['id']) if orders else None


for idx, oid in enumerate(order_list, 1):
    so_name, existing_dn = order_map[oid]
    print(f'\n[{idx}/46] {oid} | SO: {so_name} | DN: {existing_dn or "none"}', flush=True)

    try:
        # Step 1: Check SO status
        r1 = s.get(f'{BASE}/api/resource/Sales Order/{so_name}', params={
            'fields': json.dumps(['name', 'docstatus', 'status', 'shopify_order_id'])
        }, timeout=15)
        if r1.status_code != 200:
            print(f'  SO not found!', flush=True)
            results.append((oid, 'FAILED', so_name, '', '', 'SO not found'))
            continue

        so = r1.json()['data']
        shopify_id = so.get('shopify_order_id', '') or ''

        if not shopify_id:
            shopify_id = get_shopify_order_id(oid) or ''
            if shopify_id:
                print(f'  Got Shopify ID: {shopify_id}', flush=True)

        # Submit draft SO
        if so['docstatus'] == 0:
            r_sub = s.put(f'{BASE}/api/resource/Sales Order/{so_name}', json={'docstatus': 1}, timeout=30)
            if r_sub.status_code != 200:
                print(f'  SO submit FAILED: {r_sub.text[:120]}', flush=True)
                results.append((oid, 'FAILED', so_name, '', '', 'SO submit failed'))
                continue
            print(f'  SO submitted', flush=True)
        elif so['docstatus'] == 2:
            print(f'  SO is cancelled!', flush=True)
            results.append((oid, 'FAILED', so_name, '', '', 'SO cancelled'))
            continue

        # Step 2: Handle DN
        dn_name = existing_dn
        need_create_dn = False

        if existing_dn:
            r_dn = s.get(f'{BASE}/api/resource/Delivery Note/{existing_dn}', params={
                'fields': json.dumps(['name', 'docstatus', 'shopify_order_id', 'awb_number'])
            }, timeout=15)

            if r_dn.status_code == 200:
                dn = r_dn.json()['data']

                if dn['docstatus'] == 1:
                    awb = dn.get('awb_number', '') or ''
                    if awb:
                        print(f'  Already has AWB: {awb}', flush=True)
                        results.append((oid, 'EXISTS', so_name, dn_name, awb, ''))
                    else:
                        print(f'  DN submitted, no AWB', flush=True)
                        results.append((oid, 'NO_AWB', so_name, dn_name, '', 'Already submitted'))
                    continue

                elif dn['docstatus'] == 0:
                    dn_shopify = dn.get('shopify_order_id', '') or ''
                    if not dn_shopify and shopify_id:
                        s.put(f'{BASE}/api/resource/Delivery Note/{existing_dn}', json={
                            'shopify_order_id': shopify_id,
                            'shopify_order_number': oid
                        }, timeout=15)
                        print(f'  Set shopify_order_id on DN', flush=True)

                    r_sub_dn = s.put(f'{BASE}/api/resource/Delivery Note/{existing_dn}',
                                     json={'docstatus': 1}, timeout=30)
                    if r_sub_dn.status_code != 200:
                        err = r_sub_dn.text
                        if 'NegativeStockError' in err:
                            print(f'  NegativeStockError', flush=True)
                            results.append((oid, 'STOCK_ERR', so_name, dn_name, '', 'NegativeStockError'))
                        else:
                            print(f'  DN submit FAILED: {err[:100]}', flush=True)
                            results.append((oid, 'FAILED', so_name, dn_name, '', 'DN submit failed'))
                        continue
                    print(f'  DN submitted: {existing_dn}', flush=True)
                else:
                    need_create_dn = True
            else:
                need_create_dn = True
        else:
            need_create_dn = True

        if need_create_dn:
            r_mk = s.post(
                f'{BASE}/api/method/erpnext.selling.doctype.sales_order.sales_order.make_delivery_note',
                json={'source_name': so_name}, timeout=30)
            if r_mk.status_code != 200:
                print(f'  Make DN FAILED', flush=True)
                results.append((oid, 'FAILED', so_name, '', '', 'make_dn failed'))
                continue

            dn_data = r_mk.json().get('message', {})
            if shopify_id:
                dn_data['shopify_order_id'] = shopify_id
                dn_data['shopify_order_number'] = oid

            r_save = s.post(f'{BASE}/api/resource/Delivery Note', json=dn_data, timeout=30)
            if r_save.status_code != 200:
                print(f'  DN save FAILED: {r_save.text[:100]}', flush=True)
                results.append((oid, 'FAILED', so_name, '', '', 'DN save failed'))
                continue

            dn_name = r_save.json()['data']['name']
            print(f'  DN created: {dn_name}', flush=True)

            r_sub_dn = s.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',
                             json={'docstatus': 1}, timeout=30)
            if r_sub_dn.status_code != 200:
                err = r_sub_dn.text
                if 'NegativeStockError' in err:
                    print(f'  NegativeStockError', flush=True)
                    results.append((oid, 'STOCK_ERR', so_name, dn_name, '', 'NegativeStockError'))
                else:
                    print(f'  DN submit FAILED: {err[:100]}', flush=True)
                    results.append((oid, 'FAILED', so_name, dn_name, '', 'DN submit failed'))
                continue
            print(f'  DN submitted: {dn_name}', flush=True)

        # Step 3: Check AWB
        time.sleep(3)
        r_awb = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
            'fields': json.dumps(['awb_number', 'courier_partner', 'shipment_status'])
        }, timeout=15)
        d = r_awb.json()['data']
        awb = d.get('awb_number', '') or ''

        if not awb:
            time.sleep(7)
            r_awb = s.get(f'{BASE}/api/resource/Delivery Note/{dn_name}', params={
                'fields': json.dumps(['awb_number', 'courier_partner', 'shipment_status'])
            }, timeout=15)
            d = r_awb.json()['data']
            awb = d.get('awb_number', '') or ''

        courier = d.get('courier_partner', '') or ''
        if awb:
            print(f'  AWB: {awb} | {courier}', flush=True)
            results.append((oid, 'SUCCESS', so_name, dn_name, awb, courier))
        else:
            print(f'  No AWB yet', flush=True)
            results.append((oid, 'NO_AWB', so_name, dn_name, '', 'No AWB'))

    except Exception as e:
        print(f'  ERROR: {e}', flush=True)
        results.append((oid, 'ERROR', so_name, existing_dn or '', '', str(e)[:80]))

    time.sleep(0.3)

# Summary
print(f'\n{"="*130}')
print(f'{"Order ID":<14} {"Status":<12} {"SO":<30} {"DN":<26} {"AWB":<18} {"Note"}')
print(f'{"="*130}')
for oid, status, so_nm, dn, awb, note in results:
    print(f'{oid:<14} {status:<12} {so_nm:<30} {dn:<26} {awb:<18} {note}')

success = sum(1 for r in results if r[1] == 'SUCCESS')
stock_err = sum(1 for r in results if r[1] == 'STOCK_ERR')
no_awb = sum(1 for r in results if r[1] == 'NO_AWB')
failed = sum(1 for r in results if r[1] in ('FAILED', 'ERROR'))
exists = sum(1 for r in results if r[1] == 'EXISTS')
print(f'\nAWB: {success} | Stock error: {stock_err} | No AWB: {no_awb} | Already had: {exists} | Failed: {failed} | Total: {len(results)}')
