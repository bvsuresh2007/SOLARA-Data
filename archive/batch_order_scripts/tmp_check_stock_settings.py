import os, requests, json
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Check stock settings
sn = 'tmp_chk_ss'
script = """
ss = frappe.get_single('Stock Settings')
msg = "allow_negative_stock=" + str(ss.allow_negative_stock)
msg = msg + " | role_over_deliver=" + str(ss.role_allowed_to_over_deliver_receive or 'None')
frappe.response["message"] = msg
"""
r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    print(f'Stock Settings: {r2.json().get("message","")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'FAIL: {r.status_code} {r.text[:200]}')

# Check SLE sum
sn2 = 'tmp_chk_sle'
script2 = """
result = frappe.db.sql(
    "SELECT SUM(actual_qty) as total, COUNT(*) as entries "
    "FROM `tabStock Ledger Entry` "
    "WHERE item_code = 'SOL-CI-DT-101' AND warehouse = 'Main Warehouse - WTBBPL' AND is_cancelled = 0",
    as_dict=True
)
r = result[0] if result else {}
frappe.response["message"] = "SLE total=" + str(r.get('total', 0)) + " entries=" + str(r.get('entries', 0))
"""
r3 = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn2, 'script_type': 'API', 'api_method': sn2, 'script': script2, 'allow_guest': 0}, timeout=15)
if r3.status_code == 200:
    r4 = requests.get(f'{BASE}/api/method/{sn2}', headers=H, timeout=15)
    print(f'SLE: {r4.json().get("message","")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn2}', headers=H, timeout=10)
else:
    print(f'FAIL: {r3.status_code} {r3.text[:200]}')
