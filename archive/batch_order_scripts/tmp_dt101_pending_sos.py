import os, requests, json, time
from dotenv import load_dotenv
load_dotenv()

BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sku = 'SOL-CI-DT-101'
sn = 'tmp_dt101_sos'

script = """
sku = "SOL-CI-DT-101"

bundles = frappe.db.sql(
    "SELECT parent, qty FROM `tabProduct Bundle Item` WHERE item_code = %s",
    (sku,), as_dict=True
)
bundle_map = {}
for b in bundles:
    bundle_map[b['parent']] = float(b['qty'])

direct_rows = frappe.db.sql(
    "SELECT so.name as so_name, so.customer_name, soi.item_code, "
    "soi.qty, soi.delivered_qty, (soi.qty - soi.delivered_qty) as pending "
    "FROM `tabSales Order Item` soi "
    "JOIN `tabSales Order` so ON so.name = soi.parent "
    "WHERE soi.item_code = %s AND so.docstatus = 1 "
    "AND so.status NOT IN ('Completed','Cancelled','Closed') "
    "AND soi.delivered_qty < soi.qty "
    "ORDER BY pending DESC",
    (sku,), as_dict=True
)

bundle_rows = []
for bp in bundle_map:
    rows = frappe.db.sql(
        "SELECT so.name as so_name, so.customer_name, soi.item_code, "
        "soi.qty, soi.delivered_qty, (soi.qty - soi.delivered_qty) as pending "
        "FROM `tabSales Order Item` soi "
        "JOIN `tabSales Order` so ON so.name = soi.parent "
        "WHERE soi.item_code = %s AND so.docstatus = 1 "
        "AND so.status NOT IN ('Completed','Cancelled','Closed') "
        "AND soi.delivered_qty < soi.qty "
        "ORDER BY pending DESC",
        (bp,), as_dict=True
    )
    for r in rows:
        r['component_qty'] = bundle_map[bp]
        r['effective_dt101'] = float(r['pending']) * bundle_map[bp]
        bundle_rows.append(r)

out_direct = []
for r in direct_rows:
    out_direct.append(str(r['so_name']) + "|" + str(r['customer_name']) + "|" + str(r['item_code']) + "|" + str(int(r['qty'])) + "|" + str(int(r['delivered_qty'])) + "|" + str(int(r['pending'])))

out_bundle = []
for r in bundle_rows:
    out_bundle.append(str(r['so_name']) + "|" + str(r['customer_name']) + "|" + str(r['item_code']) + "|" + str(int(r['qty'])) + "|" + str(int(r['delivered_qty'])) + "|" + str(int(r['pending'])) + "|" + str(r['component_qty']) + "|" + str(r['effective_dt101']))

direct_total = 0
for r in direct_rows:
    direct_total = direct_total + float(r['pending'])

bundle_total = 0.0
for r in bundle_rows:
    bundle_total = bundle_total + float(r['effective_dt101'])

msg = "DIRECT:" + str(int(direct_total)) + ":" + str(len(direct_rows)) + "\\n"
for line in out_direct:
    msg = msg + line + "\\n"
msg = msg + "BUNDLE:" + str(int(bundle_total)) + ":" + str(len(bundle_rows)) + "\\n"
for line in out_bundle:
    msg = msg + line + "\\n"
msg = msg + "PARENTS:" + ",".join(list(bundle_map.keys()))

frappe.response["message"] = msg
"""

# Create temp server script
r = requests.post(f'{BASE}/api/resource/Server Script', headers=H,
                  json={'name': sn, 'script_type': 'API', 'api_method': sn, 'script': script, 'allow_guest': 0}, timeout=15)

if r.status_code == 200:
    r_run = requests.get(f'{BASE}/api/method/{sn}', headers=H, timeout=30)
    msg = r_run.json().get('message', '')

    if not msg:
        # Check error log
        r_err = requests.get(f'{BASE}/api/resource/Error Log', headers=H,
                             params={'filters': json.dumps([['creation','>','2026-05-04']]),
                                     'fields': json.dumps(['name','method','error']),
                                     'order_by': 'creation desc', 'limit_page_length': 3}, timeout=15)
        errs = r_err.json().get('data', [])
        for e in errs:
            print(f"Error: {e.get('method','')} - {str(e.get('error',''))[:300]}")
        requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
        exit()

    lines = msg.split('\n')

    direct_header = None
    bundle_header = None
    parents_line = None
    direct_rows = []
    bundle_rows = []
    section = None

    for line in lines:
        if line.startswith('DIRECT:'):
            direct_header = line
            section = 'direct'
        elif line.startswith('BUNDLE:'):
            bundle_header = line
            section = 'bundle'
        elif line.startswith('PARENTS:'):
            parents_line = line
        elif line.strip() and section == 'direct':
            direct_rows.append(line.split('|'))
        elif line.strip() and section == 'bundle':
            bundle_rows.append(line.split('|'))

    # Parse headers
    d_parts = direct_header.split(':') if direct_header else ['','0','0']
    b_parts = bundle_header.split(':') if bundle_header else ['','0','0']

    print(f"\n{'='*80}")
    print(f"SOL-CI-DT-101 — ALL PENDING SALES ORDERS")
    print(f"{'='*80}")

    print(f"\n--- DIRECT SOs (item_code = SOL-CI-DT-101) ---")
    print(f"Count: {d_parts[2]} SOs | Total pending qty: {d_parts[1]}")
    print(f"{'SO':<22} {'Customer':<30} {'Qty':>5} {'Dlvd':>5} {'Pend':>5}")
    print("-" * 70)
    for r in direct_rows:
        if len(r) >= 6:
            print(f"{r[0]:<22} {r[1][:29]:<30} {r[3]:>5} {r[4]:>5} {r[5]:>5}")

    print(f"\n--- BUNDLE SOs (bundles containing DT-101) ---")
    print(f"Count: {b_parts[2]} SOs | Total effective DT-101 qty: {b_parts[1]}")
    if parents_line:
        print(f"Bundle parents: {parents_line.replace('PARENTS:','')}")
    print(f"{'SO':<22} {'Customer':<22} {'Bundle SKU':<28} {'Pend':>5} {'x':>3} {'Eff':>6}")
    print("-" * 90)
    for r in bundle_rows:
        if len(r) >= 8:
            print(f"{r[0]:<22} {r[1][:21]:<22} {r[2]:<28} {r[5]:>5} {r[6]:>3} {r[7]:>6}")

    total = int(d_parts[1]) + int(float(b_parts[1]))
    print(f"\n{'='*80}")
    print(f"GRAND TOTAL DT-101 DEMAND: {total} (direct {d_parts[1]} + bundle {b_parts[1]})")
    print(f"Bin actual: 7 | Effectively short by: {total - 7}")
    print(f"{'='*80}")

    # Cleanup
    requests.delete(f'{BASE}/api/resource/Server Script/{sn}', headers=H, timeout=10)
else:
    print(f'Script create failed: {r.status_code} {r.text[:300]}')
