import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

def unblock_so(so_name, label):
    sn = 'tmp_ub_' + label
    script = """
so = '""" + so_name + """'
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
    nb = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh}, ["reserved_qty"], as_dict=True)
    frappe.response["message"] = "OK freed=" + str(int(freed)) + " new_qty=" + str(chk[0]['qty'] if chk else '?') + " bin_reserved=" + str(nb.reserved_qty if nb else '?')
"""

    print(f"\n=== Unblocking DT-101 from {so_name} ===")
    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)

    if r.status_code not in (200, 409):
        print(f'Create FAIL: {r.status_code} {r.text[:200]}')
        return

    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    msg = r2.json().get('message', '')
    if msg:
        print(f'Result: {msg}')
    else:
        sm = r2.json().get('_server_messages', '')
        print(f'Error: {sm[:300] if sm else "empty response"}')

    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)

# Unblock both
unblock_so('REZ27-00020', 'rez20v3')
unblock_so('REZ27-00001', 'rez01v3')

# Final bin check
time.sleep(1)
r_bin = requests.get(f'{BASE}/api/resource/Bin', headers=H,
    params={'filters': json.dumps([['item_code','=','SOL-CI-DT-101'],['warehouse','=','Main Warehouse - WTBBPL']]),
            'fields': json.dumps(['actual_qty','reserved_qty','projected_qty'])}, timeout=15)
b = r_bin.json().get('data', [{}])[0]
print(f'\nFinal Bin: actual={b.get("actual_qty",0)} reserved={b.get("reserved_qty",0)} projected={b.get("projected_qty",0)}')
