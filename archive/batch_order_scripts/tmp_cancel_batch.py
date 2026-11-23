import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}
CP_KEY = 'd3464616-bbd6-4874-919a-a7e8bd14d66f'

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

# Task 1: SOL1201860 - Cancel AWB 29044411172566 on Clickpost, then cancel DN+SO on Atlas
# Task 2: SOL1204932 - Cancel on Atlas
# Task 3: SOL1204799 - Cancel on Atlas

orders_to_cancel = ['SOL1201860', 'SOL1204932', 'SOL1204799']

for sol in orders_to_cancel:
    print(f'\n{"="*70}')
    print(f'=== {sol} ===')

    # Find SO
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','grand_total']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])

    if not sos:
        print(f'  SO NOT FOUND')
        continue

    for so in sos:
        so_name = so['name']
        ds = so.get('docstatus', 0)
        print(f'  SO: {so_name} | ds={ds} | {so.get("customer_name","")} | Total={so.get("grand_total",0)}')

    # Find DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                'limit_page_length': 10}, timeout=15)
    dns = r_dn.json().get('data', [])

    # Also search by customer
    if not dns:
        cust = sos[0].get('customer_name', '')
        r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['customer_name','=',cust],['against_sales_order','=',sos[0]['name']]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                    'limit_page_length': 10}, timeout=15)
        dns = r_dn2.json().get('data', [])

    for d in dns:
        print(f'  DN: {d["name"]} | ds={d.get("docstatus",0)} | AWB={d.get("awb_number","")} | {d.get("courier_partner","")}')

    # Cancel AWB on Clickpost for SOL1201860
    if sol == 'SOL1201860':
        awb = '29044411172566'
        print(f'  Cancelling AWB {awb} on Clickpost...')
        try:
            r_cancel = requests.post('https://www.clickpost.in/api/v1/cancel-order/',
                params={'username': 'solara', 'key': CP_KEY},
                json={'waybill': awb, 'cancellation_reason': 'Order cancelled by customer'},
                headers={'Content-Type': 'application/json'}, timeout=15)
            ct = r_cancel.headers.get('content-type', '')
            if 'json' in ct:
                print(f'  Clickpost cancel: {r_cancel.json().get("meta",{}).get("message","OK")}')
            else:
                print(f'  Clickpost cancel: non-JSON ({r_cancel.status_code})')
        except Exception as e:
            print(f'  Clickpost cancel ERR: {e}')

    # Cancel DNs (submitted ones)
    for d in dns:
        dn_name = d['name']
        dn_ds = d.get('docstatus', 0)

        if dn_ds == 1:
            print(f'  Cancelling DN {dn_name}...')
            r_c = requests.put(f'{BASE}/api/resource/Delivery Note/{dn_name}',
                headers=H, json={'docstatus': 2}, timeout=30)
            if r_c.status_code == 200:
                print(f'  DN {dn_name} cancelled')
            else:
                print(f'  DN cancel FAIL: {r_c.status_code} {r_c.text[:200]}')
                # Try via server script
                sn = 'tmp_cdn_' + dn_name.replace('-','_').lower()
                script = (
                    "doc = frappe.get_doc('Delivery Note', '" + dn_name + "')\n"
                    "doc.flags.ignore_validate = True\n"
                    "doc.cancel()\n"
                    "frappe.db.commit()\n"
                    "frappe.response['message'] = 'cancelled'\n"
                )
                msg = run_server_script(sn, script)
                print(f'  DN cancel via script: {msg}')
        elif dn_ds == 0:
            print(f'  Deleting draft DN {dn_name}...')
            requests.delete(f'{BASE}/api/resource/Delivery Note/{dn_name}', headers=H, timeout=15)
            print(f'  DN {dn_name} deleted')

    time.sleep(1)

    # Cancel SOs (submitted ones)
    for so in sos:
        so_name = so['name']
        so_ds = so.get('docstatus', 0)

        if so_ds == 1:
            print(f'  Cancelling SO {so_name}...')
            r_c = requests.put(f'{BASE}/api/resource/Sales Order/{so_name}',
                headers=H, json={'docstatus': 2}, timeout=30)
            if r_c.status_code == 200:
                print(f'  SO {so_name} cancelled')
            else:
                print(f'  SO cancel FAIL: {r_c.status_code} {r_c.text[:200]}')
                # Try via server script
                sn = 'tmp_cso_' + so_name.replace('-','_').lower()
                script = (
                    "doc = frappe.get_doc('Sales Order', '" + so_name + "')\n"
                    "doc.flags.ignore_validate = True\n"
                    "doc.cancel()\n"
                    "frappe.db.commit()\n"
                    "frappe.response['message'] = 'cancelled'\n"
                )
                msg = run_server_script(sn, script)
                print(f'  SO cancel via script: {msg}')
        elif so_ds == 0:
            print(f'  Deleting draft SO {so_name}...')
            requests.delete(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
            print(f'  SO {so_name} deleted')

    time.sleep(1)

print(f'\n\nDone.')
