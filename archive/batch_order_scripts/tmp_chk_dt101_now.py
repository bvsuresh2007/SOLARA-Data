import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sn = 'tmp_chk_dt101now'
script = """
result = frappe.db.sql(
    "SELECT SUM(actual_qty) as total FROM `tabStock Ledger Entry` "
    "WHERE item_code = 'SOL-CI-DT-101' AND warehouse = 'Main Warehouse - WTBBPL' AND is_cancelled = 0",
    as_dict=True
)
nb = frappe.db.get_value("Bin", {"item_code": "SOL-CI-DT-101", "warehouse": "Main Warehouse - WTBBPL"}, ["actual_qty", "reserved_qty", "projected_qty"], as_dict=True)
frappe.response["message"] = "SLE=" + str(result[0].total if result else 0) + " bin_actual=" + str(nb.actual_qty) + " bin_reserved=" + str(nb.reserved_qty) + " bin_projected=" + str(nb.projected_qty)
"""

r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    print(r2.json().get('message', ''))
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'FAIL: {r.status_code} {r.text[:200]}')
