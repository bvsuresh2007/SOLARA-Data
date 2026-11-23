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
        print(f'  Script error: {exc[:300]}')
        return None
    return msg

customers = [
    'Sridhar Yerrolla', 'Jatin .', 'Lavanya Basavaraj', 'Shaik mushraf ahammad',
    'Vani Madhav', 'Sandeep Kaur Pannu', 'Bharath Reddy', 'Sourabh Ghosh',
    'Pooja grover', 'Shruti .', 'Vatsalya S', 'Nikita',
    'PUJA CHOUDHURY', 'Kevin Gonsalvez', 'Sanju Joseph Gomes', 'Sravan Kumar',
    'Upesh Narvekar', 'Ritika katyal', 'SHABEERALI KAPPAN', 'Trushit Agrawal',
    'Pranathi Vallarapu', 'Rajesh Chinta', 'Praveen kuhad', 'Sanket Pokharkar',
    'Abhishek Raja k', 'Sonali Bhutoria', 'Tulsiram Badgujar',
    'Srinivasulu Bhuvanagiri', 'neha rai',
]

# Query in chunks - find all REP SOs per customer and their DNs/AWBs
for i in range(0, len(customers), 8):
    chunk = customers[i:i+8]
    cust_escaped = "','".join([c.replace("'", "\\'") for c in chunk])
    script = f"""results = []
custs = frappe.db.sql("SELECT DISTINCT customer, customer_name FROM `tabSales Order` WHERE customer_name IN ('{cust_escaped}') AND name LIKE 'REP-%%' AND docstatus=1", as_dict=1)
for c in custs:
    sos = frappe.db.sql("SELECT name, status FROM `tabSales Order` WHERE customer=%s AND name LIKE 'REP-%%' AND docstatus=1 ORDER BY name", c['customer'], as_dict=1)
    for so in sos:
        dns = frappe.db.sql("SELECT DISTINCT dni.parent FROM `tabDelivery Note Item` dni JOIN `tabDelivery Note` dn ON dn.name=dni.parent WHERE dni.against_sales_order=%s AND dn.docstatus=1", so['name'], as_dict=1)
        if dns:
            for d in dns:
                dn = frappe.get_doc('Delivery Note', d['parent'])
                results.append(c['customer_name'] + '|' + so['name'] + '|' + d['parent'] + '|' + str(dn.awb_number or '') + '|' + str(dn.courier_partner or '') + '|' + str(dn.posting_date or ''))
        else:
            results.append(c['customer_name'] + '|' + so['name'] + '|NO DN|||')
frappe.response['message'] = ';;'.join(results) if results else 'NONE'
"""
    msg = run_server_script(f'tmp_rep_hist_{i}', script)
    if msg and msg != 'NONE':
        for line in msg.split(';;'):
            parts = line.split('|')
            if len(parts) == 6:
                print(f'{parts[0]:<28} {parts[1]:<25} {parts[2]:<18} AWB={parts[3]:<18} {parts[4]:<12} {parts[5]}')

print('\nDONE')
