import os, requests, json, sys, time
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv('ERPNEXT_URL').rstrip('/')
H = {'Authorization': f'token {os.getenv("ERPNEXT_API_KEY")}:{os.getenv("ERPNEXT_API_SECRET")}', 'Content-Type': 'application/json'}

sols = [
    'SOL1204744','SOL1204747','SOL1204751','SOL1204765','SOL1204783',
    'SOL1204784','SOL1204786','SOL1204791','SOL1204795','SOL1204801',
    'SOL1204809','SOL1204816','SOL1204873','SOL1204894','SOL1204903',
    'SOL1204907','SOL1204918','SOL1204919','SOL1204921','SOL1204933',
    'SOL1204975','SOL1205004','SOL1205008','SOL1205015','SOL1205022',
    'SOL1205032','SOL1205037','SOL1205054','SOL1205080','SOL1205090',
    'SOL1205129',
]

print(f'{"SOL":<14} {"SO":<16} {"DS":<4} {"Customer":<25} {"Type":<8} {"Total":<10} {"DN":<20} {"DN_DS":<6} {"AWB":<22} {"Courier":<12}')
print("=" * 150)

for sol in sols:
    r_so = requests.get(f'{BASE}/api/resource/Sales Order', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','customer_name','custom_order_type','grand_total']),
                'limit_page_length': 5}, timeout=15)
    sos = r_so.json().get('data', [])

    if not sos:
        print(f'{sol:<14} {"NOT FOUND":<16}')
        time.sleep(0.2)
        continue

    so = sos[0]
    so_name = so['name']
    ds = so.get('docstatus', 0)
    cust = (so.get('customer_name', '') or '')[:24]
    otype = so.get('custom_order_type', '') or ''
    total = float(so.get('grand_total', 0) or 0)

    # DNs
    r_dn = requests.get(f'{BASE}/api/resource/Delivery Note', headers=H,
        params={'filters': json.dumps([['shopify_order_number','=',sol]]),
                'fields': json.dumps(['name','docstatus','awb_number','courier_partner']),
                'limit_page_length': 10}, timeout=15)
    dns = r_dn.json().get('data', [])

    if dns:
        for d in dns:
            awb = d.get('awb_number', '') or ''
            cp = d.get('courier_partner', '') or ''
            dn_ds = d.get('docstatus', 0)
            print(f'{sol:<14} {so_name:<16} {ds:<4} {cust:<25} {otype:<8} {total:<10.0f} {d["name"]:<20} {dn_ds:<6} {awb:<22} {cp:<12}')
    else:
        print(f'{sol:<14} {so_name:<16} {ds:<4} {cust:<25} {otype:<8} {total:<10.0f} {"NO DN":<20}')

    time.sleep(0.2)
