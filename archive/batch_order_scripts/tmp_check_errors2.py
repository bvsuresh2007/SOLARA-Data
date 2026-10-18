import os, requests, json
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# First check: did the script actually update anything?
# Check REZ27-00020 DT-101 item current qty
sn = 'tmp_chk_rez20'
script = """
row = frappe.db.sql(
    "SELECT qty, delivered_qty FROM `tabSales Order Item` "
    "WHERE parent = 'REZ27-00020' AND item_code = 'SOL-CI-DT-101' AND docstatus = 1",
    as_dict=True
)
if row:
    frappe.response["message"] = "qty=" + str(row[0]["qty"]) + " dlvd=" + str(row[0]["delivered_qty"])
else:
    frappe.response["message"] = "NOT_FOUND"
"""

r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    print(f'REZ27-00020 DT-101: {r2.json().get("message", "")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'Create fail: {r.status_code} {r.text[:200]}')

# Check REZ27-00001
sn2 = 'tmp_chk_rez01'
script2 = """
row = frappe.db.sql(
    "SELECT qty, delivered_qty FROM `tabSales Order Item` "
    "WHERE parent = 'REZ27-00001' AND item_code = 'SOL-CI-DT-101' AND docstatus = 1",
    as_dict=True
)
if row:
    frappe.response["message"] = "qty=" + str(row[0]["qty"]) + " dlvd=" + str(row[0]["delivered_qty"])
else:
    frappe.response["message"] = "NOT_FOUND"
"""
r3 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn2, 'script_type': 'API', 'api_method': sn2, 'script': script2, 'allow_guest': 0}, timeout=15)
if r3.status_code == 200:
    r4 = requests.get(f'{BASE}/api/method/{sn2}', headers=H, timeout=15)
    print(f'REZ27-00001 DT-101: {r4.json().get("message", "")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)
else:
    print(f'Create fail: {r3.status_code} {r3.text[:200]}')
