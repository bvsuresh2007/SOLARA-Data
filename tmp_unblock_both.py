import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

# Unblock DT-101 from two SOs
tasks = [
    ('REZ27-00020', 149),  # qty 257 -> 108 (delivered=108)
    ('REZ27-00001', 22),   # qty 700 -> 678 (delivered=678)
]

for so_name, to_free in tasks:
    sn = 'tmp_ub_' + so_name.replace('-', '_').lower()
    script = (
        'so = "' + so_name + '"\n'
        'sku = "SOL-CI-DT-101"\n'
        'wh = "Main Warehouse - WTBBPL"\n'
        'row = frappe.db.sql(\n'
        '    "SELECT name, qty, delivered_qty FROM `tabSales Order Item` "\n'
        '    "WHERE parent = %s AND item_code = %s AND docstatus = 1",\n'
        '    (so, sku), as_dict=True\n'
        ')\n'
        'if not row:\n'
        '    frappe.response["message"] = "NO_ROW"\n'
        'else:\n'
        '    r = row[0]\n'
        '    old_qty = float(r["qty"])\n'
        '    dlvd = float(r["delivered_qty"])\n'
        '    new_qty = dlvd\n'
        '    freed = old_qty - dlvd\n'
        '    frappe.db.sql("UPDATE `tabSales Order Item` SET qty = %s WHERE name = %s", (new_qty, r["name"]))\n'
        '    frappe.db.sql("UPDATE `tabBin` SET reserved_qty = GREATEST(reserved_qty - %s, 0) WHERE item_code = %s AND warehouse = %s", (freed, sku, wh))\n'
        '    frappe.db.commit()\n'
        '    nb = frappe.db.get_value("Bin", {"item_code": sku, "warehouse": wh}, ["actual_qty", "reserved_qty"], as_dict=True)\n'
        '    frappe.response["message"] = "OK freed=" + str(int(freed)) + " new_qty=" + str(int(new_qty)) + " bin_reserved=" + str(nb.reserved_qty if nb else "?")\n'
    )

    print(f"\n=== Unblocking {to_free} DT-101 from {so_name} ===")

    r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
        json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)

    if r.status_code != 200:
        print(f'Create FAIL: {r.status_code} {r.text[:200]}')
        continue

    time.sleep(1)
    r2 = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    msg = r2.json().get('message', '')
    print(f'Result: {msg}')

    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
    time.sleep(0.5)

# Final bin check
time.sleep(1)
r_bin = requests.get(f'{BASE}/api/resource/Bin', headers=H,
    params={'filters': json.dumps([['item_code','=','SOL-CI-DT-101'],['warehouse','=','Main Warehouse - WTBBPL']]),
            'fields': json.dumps(['actual_qty','reserved_qty','projected_qty'])}, timeout=15)
b = r_bin.json().get('data', [{}])[0]
print(f'\nFinal Bin: actual={b.get("actual_qty",0)} reserved={b.get("reserved_qty",0)} projected={b.get("projected_qty",0)}')
