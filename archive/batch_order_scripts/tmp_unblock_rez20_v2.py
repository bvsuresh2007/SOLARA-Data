import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Step 1: Unblock REZ27-00020 (149 units)
sn = 'tmp_ub_rez20_v2'
script = """
row = frappe.db.sql(
    "SELECT name, qty, delivered_qty FROM `tabSales Order Item` "
    "WHERE parent = 'REZ27-00020' AND item_code = 'SOL-CI-DT-101' AND docstatus = 1",
    as_dict=True
)
msg = ""
if row:
    r = row[0]
    old_qty = float(r['qty'])
    dlvd = float(r['delivered_qty'])
    freed = old_qty - dlvd
    frappe.db.sql(
        "UPDATE `tabSales Order Item` SET qty = delivered_qty WHERE name = %s",
        (r['name'],)
    )
    frappe.db.sql(
        "UPDATE `tabBin` SET reserved_qty = GREATEST(reserved_qty - %s, 0) WHERE item_code = 'SOL-CI-DT-101' AND warehouse = 'Main Warehouse - WTBBPL'",
        (freed,)
    )
    frappe.db.commit()
    chk = frappe.db.sql("SELECT qty FROM `tabSales Order Item` WHERE name = %s", (r['name'],), as_dict=True)
    nb = frappe.db.get_value("Bin", {"item_code": "SOL-CI-DT-101", "warehouse": "Main Warehouse - WTBBPL"}, ["reserved_qty"], as_dict=True)
    msg = "REZ20 OK freed=" + str(int(freed)) + " new_qty=" + str(chk[0]['qty'] if chk else '?') + " bin_reserved=" + str(nb.reserved_qty if nb else '?')
else:
    msg = "REZ20 NO_ROW"
frappe.response["message"] = msg
"""

print("=== REZ27-00020: Unblocking 149 DT-101 ===")
r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
    json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)
print(f'Create: {r.status_code}')
if r.status_code == 200:
    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    print(f'Status: {r2.status_code}')
    print(f'Result: {r2.json().get("message", "")}')
    if not r2.json().get("message"):
        # Check for _server_messages
        sm = r2.json().get('_server_messages', '')
        if sm:
            print(f'Server msgs: {sm[:300]}')
        print(f'Full response keys: {list(r2.json().keys())}')
        print(f'Full: {json.dumps(r2.json())[:500]}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
elif r.status_code == 409:
    # Already exists, try running
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    print(f'Result: {r2.json().get("message", "")}')
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'Body: {r.text[:300]}')
