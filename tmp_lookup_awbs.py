import os, requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv('C:/Users/accou/Documents/Projects/SOLARA-Data/.env')
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

ORDER_IDS = [
    "SOL1209695", "SOL1209706", "SOL1209722", "SOL1209739",
    "SOL1209765", "SOL1209789", "SOL1209818", "SOL1209834",
    "SOL1209843", "SOL1209866", "SOL1209871", "SOL1209894",
    "SOL1209976", "SOL1209978",
]

results = []

for oid in ORDER_IDS:
    # Step 1: Find SO
    r = requests.get(f'{BASE}/api/resource/Sales Order', headers=H, params={
        'filters': json.dumps([["shopify_order_number", "=", oid]]),
        'fields': json.dumps(["name", "customer_name", "shopify_order_number", "docstatus"]),
        'limit_page_length': 5
    })
    sos = r.json().get('data', [])
    if not sos:
        results.append({'order': oid, 'customer': '-', 'so': 'NOT FOUND', 'dn': '-', 'awb': '-', 'courier': '-'})
        continue

    for so in sos:
        so_name = so['name']
        customer = so.get('customer_name', '-')

        # Step 2: Find submitted DNs against this SO
        r2 = requests.get(f'{BASE}/api/method/frappe.client.get_list', headers=H, params={
            'doctype': 'Delivery Note',
            'filters': json.dumps([["Delivery Note Item", "against_sales_order", "=", so_name], ["docstatus", "=", 1]]),
            'fields': json.dumps(["name", "awb_number", "courier_partner", "customer_name"]),
            'limit_page_length': 10
        })
        dns = r2.json().get('message', [])
        if not dns:
            results.append({'order': oid, 'customer': customer, 'so': so_name, 'dn': 'NO DN', 'awb': '-', 'courier': '-'})
        else:
            for dn in dns:
                results.append({
                    'order': oid,
                    'customer': customer,
                    'so': so_name,
                    'dn': dn['name'],
                    'awb': dn.get('awb_number') or '-',
                    'courier': dn.get('courier_partner') or '-',
                })

# Print summary
print(f"\n{'Order ID':<14} {'Customer':<30} {'SO':<16} {'DN':<16} {'AWB':<22} {'Courier'}")
print("-" * 130)
for r in results:
    print(f"{r['order']:<14} {r['customer']:<30} {r['so']:<16} {r['dn']:<16} {r['awb']:<22} {r['courier']}")
print(f"\nTotal orders: {len(ORDER_IDS)} | Rows: {len(results)}")
