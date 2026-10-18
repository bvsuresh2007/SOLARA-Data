import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sn = 'tmp_chk_kd102'
script = """
sku = "SOL-CI-KD-102"
wh = "Main Warehouse - WTBBPL"

sle = frappe.db.sql(
    "SELECT SUM(actual_qty) as total FROM `tabStock Ledger Entry` "
    "WHERE item_code = %s AND warehouse = %s AND is_cancelled = 0",
    (sku, wh), as_dict=True
)
nb = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh},
    ["actual_qty", "reserved_qty", "projected_qty"], as_dict=True)

msg = "SLE=" + str(sle[0].total if sle and sle[0].total else 0)
if nb:
    msg = msg + " bin_actual=" + str(nb.actual_qty) + " bin_reserved=" + str(nb.reserved_qty) + " bin_projected=" + str(nb.projected_qty)
else:
    msg = msg + " NO_BIN"
frappe.response["message"] = msg
"""

r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
if r.status_code == 200:
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=15)
    print(f'SOL-CI-KD-102: {r2.json().get("message", "")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'FAIL: {r.status_code} {r.text[:200]}')

# Also check SOL1202845 failure - what SKUs does it need?
r3 = requests.get(f'{BASE}/api/resource/Delivery Note/SHPDN27-10793', headers=H, timeout=15)
dn_data = r3.json().get('data', {})
print(f'\nSOL1202845 (SHPDN27-10793):')
print(f'  docstatus={dn_data.get("docstatus","")} status={dn_data.get("status","")}')
for it in dn_data.get('items', []):
    print(f'  {it.get("item_code","?")} qty={it.get("qty",0)}')
