import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sn = 'tmp_ub_rez72'
script = """
so = 'REZ27-00072'
sku = "SOL-CI-DT-101"
wh = "Main Warehouse - WTBBPL"

row = frappe.db.sql(
    "SELECT name, qty, delivered_qty FROM `tabSales Order Item` "
    "WHERE parent = %s AND item_code = %s AND docstatus = 1",
    (so, sku), as_dict=True
)

if not row:
    frappe.response["message"] = "NO_ROW"
else:
    r = row[0]
    old_qty = float(r['qty'])
    dlvd = float(r['delivered_qty'])
    freed = old_qty - dlvd
    child_name = r['name']

    frappe.db.set_value('Sales Order Item', child_name, 'qty', dlvd, update_modified=False)

    bin_name = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh}, "name")
    if bin_name:
        old_res = frappe.db.get_value("Bin", bin_name, "reserved_qty")
        new_res = max(float(old_res or 0) - freed, 0)
        frappe.db.set_value('Bin', bin_name, 'reserved_qty', new_res, update_modified=False)

    frappe.db.commit()

    chk = frappe.db.sql("SELECT qty FROM `tabSales Order Item` WHERE name = %s", (child_name,), as_dict=True)
    nb = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh}, ["actual_qty", "reserved_qty"], as_dict=True)
    frappe.response["message"] = "OK freed=" + str(int(freed)) + " new_qty=" + str(chk[0]['qty'] if chk else '?') + " bin: actual=" + str(nb.actual_qty) + " reserved=" + str(nb.reserved_qty)
"""

r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)

if r.status_code in (200, 409):
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    print(r2.json().get('message', ''))
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'FAIL: {r.status_code} {r.text[:200]}')
