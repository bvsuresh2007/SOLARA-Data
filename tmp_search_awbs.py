import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

orders = [
    'SOL1197271',
    'SOL1201623',
    'SOL1198284',
    'REP-2627-SHP-00271',
    'SOL1196443',
    'REP-2627-OTH-00033',
    'SOL1201901',
    'REP-2627-SHP-00202',
]

print(f'{"Order":<22} {"Customer":<28} {"SO":<22} {"DN":<20} {"DS":<4} {"AWB":<22} {"Courier":<12}')
print("=" * 140)

for sol in orders:
    # Search SO by shopify_order_number
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','grand_total']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])

    if not sos:
        # Try by name directly (for REP orders)
        r_so2 = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['name','=',sol]]),
                    'fields': json.dumps(['name','docstatus','customer_name','grand_total']),
                    'limit_page_length': 5}, timeout=15)
        sos = r_so2.json().get('data', [])

    if not sos:
        # Try name like for REP with suffix
        r_so3 = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
            params={'filters': json.dumps([['name','like',sol+'%']]),
                    'fields': json.dumps(['name','docstatus','customer_name','grand_total']),
                    'limit_page_length': 5}, timeout=15)
        sos = r_so3.json().get('data', [])

    if not sos:
        print(f'{sol:<22} {"NOT FOUND":<28}')
        continue

    for so in sos:
        so_name = so['name']
        cust = (so.get('customer_name', '') or '')[:27]

        # Get DNs - search by against_sales_order or shopify_order_number
        r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
            params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                    'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                    'limit_page_length': 10}, timeout=15)
        dns = r_dn.json().get('data', [])

        if not dns:
            # Try by items against SO
            r_dn2 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
                params={'filters': json.dumps([['shopify_order_number','=',so_name]]),
                        'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                        'limit_page_length': 10}, timeout=15)
            dns = r_dn2.json().get('data', [])

        if not dns:
            # Search by customer + creation window for REP orders
            r_dn3 = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
                params={'filters': json.dumps([['against_sales_order','=',so_name]]),
                        'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                        'limit_page_length': 10}, timeout=15)
            dns = r_dn3.json().get('data', [])

        if dns:
            for d in dns:
                awb = d.get('awb_number', '') or ''
                cp = d.get('courier_partner', '') or ''
                ds = d.get('docstatus', 0)
                print(f'{sol:<22} {cust:<28} {so_name:<22} {d["name"]:<20} {ds:<4} {awb:<22} {cp:<12}')
        else:
            print(f'{sol:<22} {cust:<28} {so_name:<22} {"NO DN":<20}')

    time.sleep(0.3)
