import os, requests, json, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

def run_server_script(name, script):
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    time.sleep(1)
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': name, 'script_type': 'API', 'api_method': name, 'script': script, 'allow_guest': 0}, timeout=15)
    if r.status_code != 200: return None
    requests.post(f'{BASE}/api/method/frappe.client.clear_cache', headers=H, timeout=15)
    time.sleep(6)
    r2 = requests.get(f'{BASE}/api/method/{name}', headers=H, timeout=30)
    result = r2.json()
    msg = str(result.get('message', ''))
    exc = result.get('exception', '')
    requests.delete(f'{BASE}/api/resource/Server Script/{name}', headers=H, timeout=15)
    if exc:
        return None
    return msg

sos = [
    'REP-2627-SHP-00635', 'REP-2627-OTH-00050', 'REP-2627-SHP-00638',
    'REP-2627-SHP-00643', 'REP-2627-SHP-00618', 'REP-2627-SHP-00619',
    'REP-2627-SHP-00620', 'REP-2627-SHP-00629', 'REP-2627-SHP-00633',
    'REP-2627-SHP-00634', 'REP-2627-SHP-00636', 'REP-2627-SHP-00639',
    'REP-2627-SHP-00640', 'REP-2627-SHP-00641', 'REP-2627-SHP-00642',
    'REP-2627-SHP-00625', 'REP-2627-SHP-00626', 'REP-2627-SHP-00627',
    'REP-2627-SHP-00628', 'REP-2627-SHP-00630', 'REP-2627-SHP-00631',
    'REP-2627-SHP-00632', 'REP-2627-SHP-00621', 'REP-2627-SHP-00622',
    'REP-2627-SHP-00623', 'REP-2627-SHP-00624', 'REP-2627-OTH-00049',
    'REP-2627-SHP-00637', 'REP-2627-SHP-00644',
]

# Step 1: Get SO details (items, status, address)
print(f'{"SO":<25} {"Customer":<25} {"Status":<20} {"SKUs":<50} {"Addr"}')
print('=' * 160)

so_data = {}
for so_name in sos:
    r = requests.get(f'{BASE}/api/resource/Sales Order/{so_name}', headers=H, timeout=15)
    if r.status_code != 200:
        print(f'{so_name:<25} NOT FOUND')
        continue
    so = r.json().get('data', {})
    items = so.get('items', [])
    skus = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",1))}' for it in items])
    addr = so.get('shipping_address_name', '')
    print(f'{so_name:<25} {so.get("customer_name",""):<25} {so.get("status",""):<20} {skus:<50} {addr}')
    so_data[so_name] = so

# Step 2: Find DNs via server script (batch query)
print(f'\n\nSearching for DNs linked to these SOs...\n')

# Build batch query - process in chunks of 10
all_dn_results = {}
for i in range(0, len(sos), 10):
    chunk = sos[i:i+10]
    so_list = "','".join(chunk)
    script = f"""results = []
dns = frappe.db.sql("SELECT dni.against_sales_order as so, dni.parent as dn FROM `tabDelivery Note Item` dni JOIN `tabDelivery Note` dn ON dn.name=dni.parent WHERE dni.against_sales_order IN ('{so_list}') AND dn.docstatus != 2 GROUP BY dni.against_sales_order, dni.parent", as_dict=1)
for d in dns:
    dn_doc = frappe.get_doc('Delivery Note', d['dn'])
    results.append(d['so'] + '|' + d['dn'] + '|' + str(dn_doc.docstatus) + '|' + str(dn_doc.awb_number or '') + '|' + str(dn_doc.courier_partner or ''))
frappe.response['message'] = ';;'.join(results) if results else 'NONE'
"""
    msg = run_server_script(f'tmp_chk_dns_{i}', script)
    if msg and msg != 'NONE':
        for line in msg.split(';;'):
            parts = line.split('|')
            if len(parts) == 5:
                so_name = parts[0]
                if so_name not in all_dn_results:
                    all_dn_results[so_name] = []
                all_dn_results[so_name].append({
                    'dn': parts[1], 'docstatus': parts[2],
                    'awb': parts[3], 'courier': parts[4]
                })

# Print summary
print(f'\n{"SO":<25} {"Customer":<25} {"SKUs":<45} {"DN":<18} {"AWB":<18} {"Courier"}')
print('=' * 170)
for so_name in sos:
    if so_name not in so_data:
        print(f'{so_name:<25} NOT FOUND')
        continue
    so = so_data[so_name]
    items = so.get('items', [])
    skus = ', '.join([f'{it.get("item_code","")} x{int(it.get("qty",1))}' for it in items])
    cust = so.get('customer_name', '')

    if so_name in all_dn_results:
        for dn_info in all_dn_results[so_name]:
            print(f'{so_name:<25} {cust:<25} {skus:<45} {dn_info["dn"]:<18} {dn_info["awb"]:<18} {dn_info["courier"]}')
    else:
        print(f'{so_name:<25} {cust:<25} {skus:<45} {"NO DN":<18} {"":<18}')
