import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sn = 'tmp_unblock_rez20'
script = """
so = "REZ27-00020"
sku = "SOL-CI-DT-101"
wh = "Main Warehouse - WTBBPL"

# Get current item row
row = frappe.db.sql(
    "SELECT name, qty, delivered_qty FROM `tabSales Order Item` "
    "WHERE parent = %s AND item_code = %s AND docstatus = 1",
    (so, sku), as_dict=True
)

if not row:
    frappe.response["message"] = "NO ROW FOUND"
else:
    r = row[0]
    old_qty = float(r['qty'])
    dlvd = float(r['delivered_qty'])
    pending = old_qty - dlvd

    # Set qty = delivered_qty (no more pending)
    frappe.db.sql(
        "UPDATE `tabSales Order Item` SET qty = %s WHERE name = %s",
        (dlvd, r['name'])
    )

    # Update Bin reserved_qty
    frappe.db.sql(
        "UPDATE `tabBin` SET reserved_qty = reserved_qty - %s "
        "WHERE item_code = %s AND warehouse = %s",
        (pending, sku, wh)
    )

    frappe.db.commit()

    # Verify
    new_row = frappe.db.sql(
        "SELECT qty, delivered_qty FROM `tabSales Order Item` "
        "WHERE name = %s", (r['name'],), as_dict=True
    )
    new_bin = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh},
        ["actual_qty", "reserved_qty", "projected_qty"], as_dict=True)

    msg = "DONE"
    msg = msg + " | old_qty=" + str(old_qty) + " delivered=" + str(dlvd) + " freed=" + str(pending)
    msg = msg + " | new_qty=" + str(new_row[0]['qty']) if new_row else ""
    msg = msg + " | bin: actual=" + str(new_bin.actual_qty) + " reserved=" + str(new_bin.reserved_qty) + " projected=" + str(new_bin.projected_qty)
    frappe.response["message"] = msg
"""

r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)

if r.status_code == 200:
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    print(r2.json().get('message', ''))
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'FAIL: {r.status_code} {r.text[:300]}')
